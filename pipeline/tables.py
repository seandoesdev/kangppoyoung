"""표 처리 (설계 §7). 표 전체가 아니라 Row 단위로 정규화.

규칙: <col name>값, 병합셀 세로 반복채움(fill-down), 다단헤더 결합(부모_자식),
표 내부 섹션 행 상속, Record별 embedding_text(컬럼 의미 포함) 생성.
"""
from __future__ import annotations

import collections
import re

from .config import Config
from .extract import TableRegion
from .ids import make_table_id, norm_float, norm_text
from .raw import RawChunk

_NUM = re.compile(r"[\d,]+\s*(억원|만원|원|%|개|건|년|월|일)")
_WORDISH = re.compile(r"[가-힣A-Za-z0-9]")


def _wtok(s: str) -> list[str]:
    return [t for t in norm_text(s).split() if _WORDISH.search(t)]


def _cell(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).split()).strip()


def _is_dataish(row: list[str]) -> bool:
    """숫자/금액/긴 텍스트가 있으면 데이터 행으로 본다(헤더 밴드 종료 판정)."""
    for c in row:
        if _NUM.search(c) or len(c) > 24:
            return True
    return False


def _ffill_across(row: list[str]) -> list[str]:
    out, last = [], ""
    for c in row:
        if c:
            last = c
        out.append(c if c else last)
    return out


def _detect_header_rows(grid: list[list[str]]) -> int:
    if len(grid) < 2:
        return 1
    row0, row1 = grid[0], grid[1]
    empties0 = sum(1 for c in row0 if not c)
    if empties0 >= 1 and not _is_dataish(row1) and all(len(c) <= 16 for c in row1):
        return 2
    return 1


def _column_names(header_band: list[list[str]], ncols: int) -> list[str]:
    filled = [_ffill_across(r + [""] * (ncols - len(r))) for r in header_band]
    names: list[str] = []
    for c in range(ncols):
        parts: list[str] = []
        for r in filled:
            v = r[c] if c < len(r) else ""
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        names.append("_".join(parts) if parts else f"col{c+1}")
    # 중복 컬럼명 디스앰비그
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 1
            out.append(n)
    return out


def build_table_chunks(
    tr: TableRegion, page_no: int, heading_path: list[str], document_id: str, cfg: Config
) -> list[RawChunk]:
    grid = [[_cell(c) for c in row] for row in tr.grid]
    grid = [r for r in grid if any(r)]  # 완전 빈 행 제거
    if len(grid) < 2:
        return []
    ncols = max(len(r) for r in grid)
    grid = [r + [""] * (ncols - len(r)) for r in grid]

    hrows = _detect_header_rows(grid)
    col_names = _column_names(grid[:hrows], ncols)
    data = grid[hrows:]

    # 표 신뢰도: 열 수 일관성 + 빈칸 비율
    consistent = sum(1 for r in data if len(r) == ncols) / max(len(data), 1)
    nonempty = sum(1 for r in data for c in r if c) / max(len(data) * ncols, 1)
    table_conf = round(0.5 * consistent + 0.5 * min(nonempty * 1.5, 1.0), 2)

    grid_sig = norm_text("|".join(col_names)) + f"|{ncols}x{len(grid)}|" + norm_float(tr.x0) + norm_float(tr.y0)
    table_id = make_table_id(document_id, f"p{page_no}", grid_sig)

    # 세로 병합/섹션 상속을 위한 컬럼별 forward-fill(down)
    out: list[RawChunk] = []
    last_vals = [""] * ncols
    current_section: str | None = None
    seq = 0
    low_conf = table_conf < cfg.table_confidence_threshold

    for i, row in enumerate(data):
        # 세로 병합 채움
        filled = []
        for c in range(ncols):
            v = row[c] if c < len(row) else ""
            if v:
                last_vals[c] = v
                filled.append(v)
            else:
                filled.append(last_vals[c])

        nonempty_cells = [c for c in range(ncols) if row[c]]
        # 섹션 행: 첫 칸만 채워진 행 → 섹션 라벨로 보고 상속(레코드로 내보내지 않음)
        if len(nonempty_cells) == 1 and nonempty_cells[0] == 0 and len(row[0]) <= 40:
            current_section = row[0]
            last_vals = [""] * ncols
            last_vals[0] = row[0]
            continue

        cols = [(col_names[c], filled[c]) for c in range(ncols) if filled[c]]
        if not cols:
            continue

        rbb = tr.row_bboxes[hrows + i] if hrows + i < len(tr.row_bboxes) else (tr.x0, tr.y0, tr.x1, tr.y1)
        section_path = [current_section] if current_section else []
        core = _embedding_core(cols, section_path)
        rc = RawChunk(
            content_type="table-row",
            page_no=page_no,
            extract_method="pdf_text",
            base_conf=0.95 if not low_conf else 0.6,
            heading_path=list(heading_path),
            chapter=heading_path[0] if heading_path else None,
            section=(heading_path[1] if len(heading_path) > 1 else None),
            bbox=(rbb[0], rbb[1], rbb[2], rbb[3]),
            bbox_page=page_no,
            table_id=table_id,
            cols=cols,
            section_path=section_path,
            embedding_core=core,
            order_y=rbb[1],
            order_x=rbb[0],
        )
        if low_conf:
            rc.needs_review = True
            rc.review_reasons.append("table_fallback")
        out.append(rc)
        seq += 1

    # 추출 손실 감지: 구조화한 셀이 표 영역 원문 단어를 충분히 담지 못하면 text 폴백(무손실 보장)
    total = collections.Counter(_wtok(" ".join(tr.words)))
    if total:
        covered = collections.Counter()
        for rc in out:
            for n, v in (rc.cols or []):
                covered.update(_wtok(v))
                covered.update(_wtok(n.replace("_", " ")))
            covered.update(_wtok(" ".join(rc.section_path)))
        recall = sum(min(c, covered[w]) for w, c in total.items()) / sum(total.values())
        if recall < cfg.table_word_coverage_min:
            return _fallback_text(tr, page_no, heading_path, cfg)
    return out


def _fallback_text(tr: TableRegion, page_no: int, heading_path: list[str], cfg: Config) -> list[RawChunk]:
    """표 구조 인식이 불충분하면 영역 원문을 text 청크로 보존한다(구조는 잃되 텍스트는 무손실)."""
    out: list[RawChunk] = []
    words = [w for w in tr.words if w]
    if not words:
        return out
    buf: list[str] = []
    n = 0
    for w in words:
        buf.append(w)
        n += len(w) + 1
        if n >= cfg.max_chunk_chars:
            out.append(_fb_chunk(tr, page_no, heading_path, " ".join(buf), len(out)))
            buf, n = [], 0
    if buf:
        out.append(_fb_chunk(tr, page_no, heading_path, " ".join(buf), len(out)))
    return out


def _fb_chunk(tr: TableRegion, page_no: int, heading_path: list[str], text: str, k: int) -> RawChunk:
    return RawChunk(
        content_type="text",
        page_no=page_no,
        extract_method="pdf_text",
        base_conf=0.6,
        heading_path=list(heading_path),
        chapter=heading_path[0] if heading_path else None,
        section=(heading_path[1] if len(heading_path) > 1 else None),
        bbox=(tr.x0, tr.y0, tr.x1, tr.y1),
        bbox_page=page_no,
        text=text,
        needs_review=True,
        review_reasons=["table_fallback"],
        order_y=tr.y0 + k * 0.01,
        order_x=tr.x0,
    )


def _embedding_core(cols: list[tuple[str, str]], section_path: list[str]) -> str:
    """컬럼 의미를 포함한 검색용 핵심 문장(결정적 템플릿)."""
    prefix = f"[{' / '.join(section_path)}] " if section_path else ""
    body = ", ".join(f"{n}: {v}" for n, v in cols)
    return f"{prefix}{body}"
