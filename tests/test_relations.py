"""관계 그래프 테스트 (설계 §10). 읽기순 previous/next, 같은 표 행끼리 related, dangling 없음."""
from __future__ import annotations

from pipeline import relations as R
from tests.conftest import (
    make_figure_chunk,
    make_table_note_chunk,
    make_table_row_chunk,
    make_text_chunk,
)


def test_previous_next_chain_in_reading_order():
    chunks = [make_text_chunk(f"c_{i:04d}", text=f"문단 {i}") for i in range(4)]
    R.link(chunks)
    assert chunks[0].meta.previous_chunk_id is None
    assert chunks[-1].meta.next_chunk_id is None
    for i in range(1, len(chunks)):
        assert chunks[i].meta.previous_chunk_id == chunks[i - 1].meta.chunk_id
        assert chunks[i - 1].meta.next_chunk_id == chunks[i].meta.chunk_id


def test_same_table_rows_are_related_bidirectionally():
    rows = [make_table_row_chunk(f"c_r{i}", "tbl_1", i) for i in range(3)]
    R.link(rows)
    for r in rows:
        sibs = set(r.meta.related_chunk_ids)
        assert r.meta.chunk_id not in sibs                 # 자기 자신 제외
        assert sibs == {x.meta.chunk_id for x in rows} - {r.meta.chunk_id}


def test_no_dangling_references():
    chunks = [make_text_chunk("c_0001"), make_table_row_chunk("c_r0", "tbl_1", 0),
              make_table_row_chunk("c_r1", "tbl_1", 1)]
    R.link(chunks)
    ids = {c.meta.chunk_id for c in chunks}
    for c in chunks:
        m = c.meta
        for ref in [m.previous_chunk_id, m.next_chunk_id, m.parent_chunk_id,
                    *m.related_chunk_ids]:
            assert ref is None or ref in ids


def test_table_note_linked_to_rows_bidirectionally():
    """표 주석 ↔ 같은 table_id 행을 양방향 related로 연결(§10.2)."""
    note = make_table_note_chunk("c_note", "tbl_1")
    rows = [make_table_row_chunk(f"c_r{i}", "tbl_1", i) for i in range(2)]
    R.link([note, *rows])
    for r in rows:
        assert "c_note" in r.meta.related_chunk_ids       # 행 → 주석
    note_rel = set(note.meta.related_chunk_ids)
    assert {"c_r0", "c_r1"} <= note_rel                    # 주석 → 모든 행


def test_figure_chunks_related_by_figure_id_bidirectionally():
    """같은 figure_id 청크들을 양방향 related로 연결(§10.2)."""
    figs = [make_figure_chunk(f"c_f{i}", "fig_1", i) for i in range(3)]
    R.link(figs)
    for f in figs:
        sibs = set(f.meta.related_chunk_ids)
        assert f.meta.chunk_id not in sibs
        assert sibs == {x.meta.chunk_id for x in figs} - {f.meta.chunk_id}


def test_related_ids_are_sorted_set():
    """related_chunk_ids는 sorted(set(...))로 결정적(중복 없음·정렬)."""
    rows = [make_table_row_chunk(f"c_r{i}", "tbl_1", i) for i in range(3)]
    note = make_table_note_chunk("c_note", "tbl_1")
    R.link([note, *rows])
    for ch in [note, *rows]:
        rel = ch.meta.related_chunk_ids
        assert rel == sorted(set(rel))


def test_no_dangling_in_cross_type_related():
    note = make_table_note_chunk("c_note", "tbl_1")
    rows = [make_table_row_chunk(f"c_r{i}", "tbl_1", i) for i in range(2)]
    figs = [make_figure_chunk(f"c_f{i}", "fig_1", i) for i in range(2)]
    chunks = [note, *rows, *figs]
    R.link(chunks)
    ids = {c.meta.chunk_id for c in chunks}
    for c in chunks:
        for ref in c.meta.related_chunk_ids:
            assert ref in ids


def test_parent_points_to_nearest_heading_ancestor():
    """본문 청크 parent = heading_path가 자기 경로의 진부분집합(prefix)인 가장 가까운 선행 청크(§10.1)."""
    c0 = make_text_chunk("c_0000", text="장 도입", heading_path=["제1장"])
    c1 = make_text_chunk("c_0001", text="절 본문", heading_path=["제1장", "1절"])
    c2 = make_text_chunk("c_0002", text="절 본문2", heading_path=["제1장", "1절"])
    R.link([c0, c1, c2])
    assert c0.meta.parent_chunk_id is None              # 최상위 — 조상 없음
    assert c1.meta.parent_chunk_id == "c_0000"          # ["제1장"]이 prefix
    assert c2.meta.parent_chunk_id == "c_0000"          # 동일 깊이 형제는 조상 c0로


def test_table_row_parent_is_table_anchor():
    """표 Record/주석 parent = 그 표의 앵커(첫 행) 청크(§10.1 표 헤더 대용). 앵커 자신은 표 parent 없음."""
    rows = [make_table_row_chunk(f"c_r{i}", "tbl_1", i) for i in range(3)]
    R.link(rows)
    anchor = rows[0].meta.chunk_id
    assert rows[0].meta.parent_chunk_id is None         # 앵커는 자기 자신을 가리키지 않음
    assert rows[1].meta.parent_chunk_id == anchor
    assert rows[2].meta.parent_chunk_id == anchor
