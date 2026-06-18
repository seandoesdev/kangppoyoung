"""관계 그래프 (설계 §10). 읽기 순서로 previous/next를 잇고, 표 행끼리 table_id로 related를 건다."""
from __future__ import annotations

from collections import defaultdict

from . import models as M


_TABLE_KINDS = (M.ContentType.TABLE_ROW, M.ContentType.TABLE_NOTE)


def link(chunks: list[M.Chunk]) -> None:
    """chunks는 이미 읽기 순서(page, y, x)로 정렬돼 있다고 가정. in-place로 관계를 채운다."""
    n = len(chunks)
    for i, ch in enumerate(chunks):
        if i > 0:
            ch.meta.previous_chunk_id = chunks[i - 1].meta.chunk_id
        if i < n - 1:
            ch.meta.next_chunk_id = chunks[i + 1].meta.chunk_id

    # parent (§10.1 Pass1): 표 Record/주석 → 그 표의 앵커(첫 행) 청크(표 헤더 대용),
    # 그 외 본문 청크 → heading_path가 자기 경로의 진부분집합(prefix)인 가장 가까운 선행 청크.
    table_anchor: dict[str, str] = {}
    for ch in chunks:
        tid = ch.meta.table_id
        if tid and ch.meta.content_type in _TABLE_KINDS:
            table_anchor.setdefault(tid, ch.meta.chunk_id)
    for i, ch in enumerate(chunks):
        m = ch.meta
        parent: str | None = None
        if m.table_id and m.content_type in _TABLE_KINDS:
            anchor = table_anchor.get(m.table_id)
            if anchor and anchor != m.chunk_id:
                parent = anchor
        if parent is None and m.heading_path:
            hp = m.heading_path
            for j in range(i - 1, -1, -1):
                cand = chunks[j].meta.heading_path
                if len(cand) < len(hp) and hp[: len(cand)] == cand:
                    parent = chunks[j].meta.chunk_id
                    break
        m.parent_chunk_id = parent

    # related (§10.2 Pass2): 구조로 안 잡히는 의미 연관을 결정적·양방향으로 연결.
    # 누적 후 마감 시 sorted(set(...)) → 재실행 안정, dangling 없음.
    rel: dict[str, set[str]] = defaultdict(set)

    def _add(a: str, b: str) -> None:
        if a != b:
            rel[a].add(b)
            rel[b].add(a)

    # 같은 표(table_id): 행↔행, 표주석↔행 양방향(표설명↔Record).
    by_table: dict[str, dict[str, list[M.Chunk]]] = defaultdict(lambda: {"rows": [], "notes": []})
    for ch in chunks:
        tid = ch.meta.table_id
        if not tid:
            continue
        if ch.meta.content_type == M.ContentType.TABLE_ROW:
            by_table[tid]["rows"].append(ch)
        elif ch.meta.content_type == M.ContentType.TABLE_NOTE:
            by_table[tid]["notes"].append(ch)
    for grp in by_table.values():
        rows, notes = grp["rows"], grp["notes"]
        row_ids = [r.meta.chunk_id for r in rows]
        for r in rows:
            for other in row_ids:
                _add(r.meta.chunk_id, other)
        for note in notes:
            for r in rows:
                _add(note.meta.chunk_id, r.meta.chunk_id)

    # 같은 도형(figure_id): node/edge/desc/step 등 모든 조각을 양방향 연결.
    by_figure: dict[str, list[M.Chunk]] = defaultdict(list)
    for ch in chunks:
        if ch.meta.figure_id:
            by_figure[ch.meta.figure_id].append(ch)
    for figs in by_figure.values():
        fids = [f.meta.chunk_id for f in figs]
        for f in figs:
            for other in fids:
                _add(f.meta.chunk_id, other)

    for ch in chunks:
        ch.meta.related_chunk_ids = sorted(rel.get(ch.meta.chunk_id, set()))
