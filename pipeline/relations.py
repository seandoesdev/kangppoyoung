"""관계 그래프 (설계 §10). 읽기 순서로 previous/next를 잇고, 표 행끼리 table_id로 related를 건다."""
from __future__ import annotations

from collections import defaultdict

from . import models as M


def link(chunks: list[M.Chunk]) -> None:
    """chunks는 이미 읽기 순서(page, y, x)로 정렬돼 있다고 가정. in-place로 관계를 채운다."""
    n = len(chunks)
    for i, ch in enumerate(chunks):
        if i > 0:
            ch.meta.previous_chunk_id = chunks[i - 1].meta.chunk_id
        if i < n - 1:
            ch.meta.next_chunk_id = chunks[i + 1].meta.chunk_id

    # 같은 표의 행들을 related로 연결(표설명↔Record 대용: 행 상호 참조). 상한으로 메타 폭주 방지.
    by_table: dict[str, list[M.Chunk]] = defaultdict(list)
    for ch in chunks:
        if ch.meta.content_type == M.ContentType.TABLE_ROW and ch.meta.table_id:
            by_table[ch.meta.table_id].append(ch)
    for rows in by_table.values():
        ids = [r.meta.chunk_id for r in rows]
        for r in rows:
            sib = [x for x in ids if x != r.meta.chunk_id][:8]
            r.meta.related_chunk_ids = sib
