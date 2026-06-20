"""청크 품질 개선 스테이지 테스트 (docs/plan/chunk_merge_impl_plan.md §12).

경계 결정을 mock으로 주입해 LLM 없이 구성의 **무손실·결정론**을 검증한다.
"""
from __future__ import annotations

from pipeline import merge as MG
from pipeline import models as M
from pipeline import relations as R
from pipeline.config import Config
from tests.conftest import make_table_row_chunk, make_text_chunk


class _MergeAll:
    """모든 경계 false → 크기 한도 내에서 가능한 한 병합(테스트용)."""

    def decide(self, run, cfg):
        return [False] * (len(run) - 1)


class _BoundaryAt:
    """지정한 인덱스(i, i+1 사이)에만 경계."""

    def __init__(self, idxs):
        self.idxs = set(idxs)

    def decide(self, run, cfg):
        return [i in self.idxs for i in range(len(run) - 1)]


def _section(prefix: str, n: int, heading, page=1):
    return [make_text_chunk(f"c_{prefix}{i}", text=f"{prefix}{i} 문장", page_no=page,
                            heading_path=list(heading)) for i in range(n)]


def test_no_merge_decider_preserves_chunks():
    chunks = _section("a", 3, ["제1장", "1절"])
    out = MG.merge_chunks(chunks, Config(), MG.NoMergeDecider())
    assert [c.meta.chunk_id for c in out] == [c.meta.chunk_id for c in chunks]


def test_merge_all_combines_same_section_losslessly():
    chunks = _section("a", 4, ["제1장", "융자절차"])
    out = MG.merge_chunks(chunks, Config(), _MergeAll())
    assert len(out) == 1
    merged = out[0]
    assert merged.meta.content_type is M.ContentType.TEXT
    # 무손실: 모든 멤버 텍스트가 병합 텍스트에 보존된다.
    for ch in chunks:
        assert MG.member_text(ch) in merged.content.text


def test_heading_boundary_blocks_merge():
    chunks = _section("a", 2, ["제1장", "1절"]) + _section("b", 2, ["제1장", "2절"])
    out = MG.merge_chunks(chunks, Config(), _MergeAll())
    # 서로 다른 heading_path는 한 단위로 묶이지 않는다 → 2개 병합 단위.
    assert len(out) == 2
    assert {tuple(c.meta.heading_path) for c in out} == {("제1장", "1절"), ("제1장", "2절")}


def test_non_mergeable_chunk_breaks_run():
    rows = _section("a", 2, ["제1장", "1절"])
    table = make_table_row_chunk("c_tbl", "tbl_1", 0)  # 표 행: 병합 대상 아님
    more = _section("b", 2, ["제1장", "1절"])
    out = MG.merge_chunks(rows + [table] + more, Config(), _MergeAll())
    # [a0,a1] 병합 / 표행 통과 / [b0,b1] 병합 → 3개.
    assert len(out) == 3
    assert out[1].meta.chunk_id == "c_tbl"
    assert out[1].meta.content_type is M.ContentType.TABLE_ROW


def test_size_limit_forces_split():
    chunks = _section("a", 3, ["제1장", "1절"])           # 각 멤버 텍스트 길이 ~5
    cfg = Config(max_chunk_chars=len(MG.member_text(chunks[0])) * 2 + 1)  # 2개까지만 허용
    out = MG.merge_chunks(chunks, cfg, _MergeAll())
    # a0+a1 병합, a2는 크기 강제 경계로 분리 → 2개.
    assert len(out) == 2
    assert MG.member_text(chunks[0]) in out[0].content.text
    assert MG.member_text(chunks[1]) in out[0].content.text
    assert out[1].meta.chunk_id == chunks[2].meta.chunk_id


def test_merge_is_deterministic():
    chunks = _section("a", 3, ["제1장", "1절"])
    out1 = MG.merge_chunks(chunks, Config(), _BoundaryAt([1]))
    out2 = MG.merge_chunks(chunks, Config(), _BoundaryAt([1]))
    assert [c.meta.chunk_id for c in out1] == [c.meta.chunk_id for c in out2]
    assert [c.content.text for c in out1] == [c.content.text for c in out2]


def test_relations_intact_after_merge():
    chunks = _section("a", 4, ["제1장", "융자절차"])
    out = MG.merge_chunks(chunks, Config(), _BoundaryAt([2]))  # [a0,a1,a2] | [a3]
    R.link(out)
    ids = {c.meta.chunk_id for c in out}
    for c in out:
        m = c.meta
        for ref in [m.previous_chunk_id, m.next_chunk_id, m.parent_chunk_id, *m.related_chunk_ids]:
            assert ref is None or ref in ids


def test_unique_chunk_ids_after_merge():
    chunks = _section("a", 5, ["제1장", "1절"]) + _section("b", 5, ["제1장", "2절"])
    out = MG.merge_chunks(chunks, Config(), _MergeAll())
    ids = [c.meta.chunk_id for c in out]
    assert len(ids) == len(set(ids))
