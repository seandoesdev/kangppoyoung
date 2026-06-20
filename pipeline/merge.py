"""청크 품질 개선 스테이지 (docs/plan/chunk_merge_impl_plan.md).

build 직후의 Chunk 리스트에서, 같은 leaf 섹션(heading_path)의 연속 텍스트형 청크를
'업무적으로 유효한 단위'로 병합한다. 경계 판단은 BoundaryDecider(온라인 LLM 또는 테스트용
결정)에 위임하고, 청크 구성은 이 모듈이 무손실·결정론으로 확정한다.

핵심 불변식:
- LLM은 '경계'만 판단하고 텍스트는 한 글자도 쓰지 않는다.
- 병합 텍스트 = 멤버 텍스트를 순서대로 연결 → 원문 문자 보존(verify 보존율 게이트 통과).
- 경계 결정이 같으면 결과는 byte-identical(순수 함수). 결정은 provider가 캐시한다.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from . import ids as I
from . import models as M
from .config import Config

# 병합 대상(텍스트형). 표 행/주석·시각자료는 구조·링크가 있어 병합하지 않고 경계로 둔다.
_MERGEABLE = frozenset({M.ContentType.TEXT, M.ContentType.LIST_ITEM})


def member_text(ch: M.Chunk) -> str:
    """병합 시 사용할 청크 대표 텍스트(verify 보존 파트와 동일 문자 집합)."""
    c = ch.content
    if c.kind == "list-item":
        marker = (c.marker + " ") if c.marker else ""
        return (marker + c.text).strip()
    return (getattr(c, "text", "") or "").strip()


# ─────────────────────────── 경계 판단 인터페이스 ───────────────────────────
@runtime_checkable
class BoundaryDecider(Protocol):
    def decide(self, run: list[M.Chunk], cfg: Config) -> list[bool]:
        """run[i]와 run[i+1] 사이에 단위 경계가 있으면 True. 길이 len(run)-1."""
        ...


class NoMergeDecider:
    """모든 경계 True → 병합하지 않음(원본 보존). 롤백/기본값."""

    def decide(self, run: list[M.Chunk], cfg: Config) -> list[bool]:  # noqa: ARG002
        return [True] * (len(run) - 1)


# ─────────────────────────── 오케스트레이션 ───────────────────────────
def merge_chunks(chunks: list[M.Chunk], cfg: Config, decider: BoundaryDecider) -> list[M.Chunk]:
    """연속 텍스트형 run을 decider 경계 + 크기 한도로 분절해 병합한다(무손실·결정론)."""
    out: list[M.Chunk] = []
    i, n = 0, len(chunks)
    while i < n:
        ch = chunks[i]
        if ch.meta.content_type not in _MERGEABLE:
            out.append(ch)
            i += 1
            continue
        hp = ch.meta.heading_path
        j = i + 1
        while (j < n and chunks[j].meta.content_type in _MERGEABLE
               and chunks[j].meta.heading_path == hp):
            j += 1
        for group in _segment(chunks[i:j], decider, cfg):
            out.append(group[0] if len(group) == 1 else _merge_group(group))
        i = j
    _ensure_unique_ids(out)
    return out


def maybe_merge(chunks: list[M.Chunk], cfg: Config) -> list[M.Chunk]:
    """cfg로 게이트. merge 비활성 또는 provider 없음(키 없음)이면 원본을 그대로 반환."""
    decider = get_decider(cfg)
    if decider is None:
        return chunks
    return merge_chunks(chunks, cfg, decider)


def get_decider(cfg: Config) -> BoundaryDecider | None:
    if not cfg.merge_enabled:
        return None
    from .providers_merge import get_boundary_decider  # 선택적 온라인 백엔드
    return get_boundary_decider(cfg)


# ─────────────────────────── 분절 · 구성(프로그래머틱) ───────────────────────────
def _segment(run: list[M.Chunk], decider: BoundaryDecider, cfg: Config) -> list[list[M.Chunk]]:
    if len(run) == 1:
        return [run]
    cuts = decider.decide(run, cfg)
    if len(cuts) != len(run) - 1:  # 방어: 잘못된 길이는 '병합 안 함'으로 안전 처리
        cuts = [True] * (len(run) - 1)
    groups: list[list[M.Chunk]] = []
    cur = [run[0]]
    size = len(member_text(run[0]))
    for k in range(1, len(run)):
        nxt = len(member_text(run[k]))
        force = (size + nxt) > cfg.max_chunk_chars  # 크기 강제 경계(과병합 방지)
        if cuts[k - 1] or force:
            groups.append(cur)
            cur = [run[k]]
            size = nxt
        else:
            cur.append(run[k])
            size += nxt
    groups.append(cur)
    return groups


def _merge_group(group: list[M.Chunk]) -> M.Chunk:
    """그룹을 단일 TextContent 청크로 무손실 구성. 멤버 텍스트를 순서대로 연결한다."""
    first = group[0].meta
    document_id, file_name = first.document_id, first.file_name
    merged_text = "\n".join(t for t in (member_text(ch) for ch in group) if t)
    heading_path = list(first.heading_path)

    pages = sorted({p for ch in group for p in _pages(ch.meta)})
    if len(pages) <= 1:
        page_no = pages[0] if pages else first.page_no
        page_range = None
        bbox = _bounding_bbox(group, page_no)
    else:
        page_no = None
        page_range = (pages[0], pages[-1])
        bbox = first.bbox  # 다중 페이지: 첫 멤버 bbox를 앵커로(위치 복원)

    pa = I.page_anchor(page_no, page_range)
    spath = I.structural_path(heading_path, None)
    chunk_id = I.make_chunk_id(document_id, "text", pa, spath, I.norm_text(merged_text), 0)
    char_range = None if bbox else (0, len(merged_text))  # bbox 없으면 char_range로 위치 불변식 충족
    locator = " > ".join(heading_path) if heading_path else None
    sl = M.SourceLocation(
        file_name=file_name, document_id=document_id, page_no=page_no, page_range=page_range,
        bbox=bbox, extract_method=M.ExtractMethod.PDF_TEXT, heading_path=heading_path,
        locator=locator, char_range=char_range,
    )
    reasons = sorted({r for ch in group for r in ch.meta.review_reasons})
    meta = M.Meta(
        chunk_id=chunk_id, document_id=document_id, file_name=file_name,
        page_no=page_no, page_range=page_range, content_type=M.ContentType.TEXT,
        chapter=first.chapter, section=first.section, subsection=first.subsection,
        heading_path=heading_path, extract_method=M.ExtractMethod.PDF_TEXT,
        confidence=min(ch.meta.confidence for ch in group), bbox=bbox,
        related_chunk_ids=[], source_location=sl,
        needs_review=any(ch.meta.needs_review for ch in group), review_reasons=reasons,
    )
    return M.Chunk(meta=meta, content=M.TextContent(text=merged_text))


def _pages(m: M.Meta) -> list[int]:
    if m.page_range:
        return list(range(m.page_range[0], m.page_range[1] + 1))
    return [m.page_no] if m.page_no else []


def _bounding_bbox(group: list[M.Chunk], page_no: int | None) -> M.BBox | None:
    boxes = [ch.meta.bbox for ch in group
             if ch.meta.bbox and (page_no is None or ch.meta.bbox.page == page_no)]
    if not boxes:
        return None
    return M.BBox(
        page=boxes[0].page,
        x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
    )


def _ensure_unique_ids(chunks: list[M.Chunk]) -> None:
    """병합으로 드물게 생길 수 있는 chunk_id 충돌을 seq 증가로 해소(결정적)."""
    seen: set[str] = set()
    for ch in chunks:
        m = ch.meta
        if m.chunk_id not in seen:
            seen.add(m.chunk_id)
            continue
        pa = I.page_anchor(m.page_no, m.page_range)
        spath = I.structural_path(m.heading_path, m.table_id or m.figure_id)
        normc = I.norm_text(member_text(ch))
        seq = 1
        while True:
            new = I.make_chunk_id(m.document_id, m.content_type.value, pa, spath, normc, seq)
            if new not in seen:
                m.chunk_id = new
                seen.add(new)
                break
            seq += 1
