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


def _header_signature(grid: list[list]) -> tuple[int, str] | None:
    """표 첫 행(헤더 추정)의 (열 수, 정규화 텍스트) 시그니처. 빈 표면 None.

    페이지 넘김 병합(§7.5)에서 열 수+헤더 동일성 보수 판정에 쓴다."""
    rows = [[_cell(c) for c in row] for row in grid]
    rows = [r for r in rows if any(r)]
    if not rows:
        return None
    ncols = max(len(r) for r in rows)
    head = rows[0] + [""] * (ncols - len(rows[0]))
    return (ncols, norm_text("|".join(head)))


def merge_cross_page(
    page_tables: list[tuple[int, TableRegion]],
) -> list[tuple[int, tuple[int, int] | None, TableRegion]]:
    """연속 페이지에서 같은 열 시그니처(열 수+헤더 동일)인 표를 논리 1표로 병합(§7.5).

    입력: 문서 읽기순 (page_no, TableRegion). 보수적으로 (열 수+헤더 동일 AND 연속 페이지)일
    때만 병합한다. 반환: (anchor_page_no, page_range|None, TableRegion). 단일 표는 page_range=None.
    행은 절대 잃지 않는다(병합 시 반복 헤더 1벌만 제거)."""
    out: list[tuple[int, tuple[int, int] | None, TableRegion]] = []
    i = 0
    n = len(page_tables)
    while i < n:
        first_page, base = page_tables[i]
        sig = _header_signature(base.grid)
        last_page = first_page
        merged_grid = [list(r) for r in base.grid]
        merged_rbb = list(base.row_bboxes)
        merged_words = list(base.words)
        x0, y0, x1, y1 = base.x0, base.y0, base.x1, base.y1
        j = i + 1
        while (
            sig is not None
            and j < n
            and page_tables[j][0] == last_page + 1
            and _header_signature(page_tables[j][1].grid) == sig
        ):
            nxt = page_tables[j][1]
            # 반복 헤더(첫 비어있지 않은 행) 1벌 제거 후 데이터 행 append(무손실, 헤더만 1회).
            ngrid = [list(r) for r in nxt.grid]
            ndata = ngrid[1:] if ngrid else []
            merged_grid.extend(ndata)
            merged_rbb.extend(nxt.row_bboxes[1:] if nxt.row_bboxes else [])
            merged_words.extend(nxt.words)
            x0, y0 = min(x0, nxt.x0), min(y0, nxt.y0)
            x1, y1 = max(x1, nxt.x1), max(y1, nxt.y1)
            last_page = page_tables[j][0]
            j += 1
        if last_page > first_page:
            tr = TableRegion(
                x0=x0, y0=y0, x1=x1, y1=y1,
                grid=merged_grid, row_bboxes=merged_rbb, words=merged_words,
            )
            out.append((first_page, (first_page, last_page), tr))
        else:
            out.append((first_page, None, base))
        i = j
    return out


def build_table_chunks(
    tr: TableRegion,
    page_no: int,
    heading_path: list[str],
    document_id: str,
    cfg: Config,
    page_range: tuple[int, int] | None = None,
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
    # 병합 표는 page_range 앵커(p{first}-{last})로 단일 table_id 유지(§7.5).
    anchor = f"p{page_range[0]}-{page_range[1]}" if page_range else f"p{page_no}"
    table_id = make_table_id(document_id, anchor, grid_sig)

    # 세로 병합/섹션 상속을 위한 컬럼별 forward-fill(down)
    out: list[RawChunk] = []
    last_vals = [""] * ncols
    # 표 내부 섹션 행이 나오기 전까지는 표 위치의 heading 컨텍스트를 섹션으로 상속(§7.4).
    current_section: list[str] = list(heading_path)
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
        # 섹션 행: 첫 칸만 채워진 행 → 섹션 라벨로 보고 상속(레코드로 내보내지 않음).
        # 표 내부 섹션 라벨이 등장하면 heading 상속을 대체한다(in-table 우선, §7.4).
        if len(nonempty_cells) == 1 and nonempty_cells[0] == 0 and len(row[0]) <= 40:
            current_section = [row[0]]
            last_vals = [""] * ncols
            last_vals[0] = row[0]
            continue

        cols = [(col_names[c], filled[c]) for c in range(ncols) if filled[c]]
        if not cols:
            continue

        rbb = tr.row_bboxes[hrows + i] if hrows + i < len(tr.row_bboxes) else (tr.x0, tr.y0, tr.x1, tr.y1)
        section_path = list(current_section)
        core = _embedding_core(cols, section_path)
        rc = RawChunk(
            content_type="table-row",
            page_no=page_no,
            page_range=page_range,
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
