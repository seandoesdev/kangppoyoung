"""표 페이지 넘김 병합 테스트 (설계 §7.5). 같은 열 시그니처+연속 페이지 → 단일 table_id, page_range[first,last]."""
from __future__ import annotations

from pipeline.config import Config
from pipeline.extract import TableRegion
from pipeline.tables import build_table_chunks, merge_cross_page


def _region(grid, y0=100.0):
    nrows = len(grid)
    rbb = [(72.0, y0 + 20 * i, 520.0, y0 + 18 + 20 * i) for i in range(nrows)]
    words = []
    for r in grid:
        for c in r:
            words.extend(str(c).split())
    return TableRegion(
        x0=72.0, y0=y0, x1=520.0, y1=y0 + 20 * nrows, grid=grid, row_bboxes=rbb, words=words
    )


def test_continuation_table_merges_into_single_logical_table():
    g1 = [["산업명", "지원금액"], ["자동차 부품", "5억원"], ["조선 기자재", "3억원"]]
    g2 = [["산업명", "지원금액"], ["반도체 장비", "7억원"]]  # 다음 페이지에서 헤더 반복 + 데이터 이어짐
    merged = merge_cross_page([(2, _region(g1)), (3, _region(g2))])
    assert len(merged) == 1, "연속 페이지 동일 헤더 표는 1개로 병합"
    page_no, page_range, tr = merged[0]
    assert page_range == (2, 3)


def test_merged_rows_share_one_table_id_and_page_range():
    g1 = [["산업명", "지원금액"], ["자동차 부품", "5억원"]]
    g2 = [["산업명", "지원금액"], ["반도체 장비", "7억원"]]
    merged = merge_cross_page([(2, _region(g1)), (3, _region(g2))])
    page_no, page_range, tr = merged[0]
    rows = build_table_chunks(tr, page_no, ["제2장"], "d_x", Config(), page_range=page_range)
    ids = {r.table_id for r in rows}
    assert len(ids) == 1 and next(iter(ids)).startswith("tbl_")
    assert all(r.page_range == (2, 3) for r in rows)
    # 두 페이지의 데이터 행이 모두 보존(무손실)
    names = {dict(r.cols)["산업명"] for r in rows}
    assert names == {"자동차 부품", "반도체 장비"}


def test_different_signature_is_not_merged():
    g1 = [["산업명", "지원금액"], ["자동차 부품", "5억원"]]
    g2 = [["조항", "내용", "비고"], ["제1조", "목적", "-"]]  # 열 수/헤더 다름 → 병합 금지
    merged = merge_cross_page([(2, _region(g1)), (3, _region(g2))])
    assert len(merged) == 2, "시그니처 불일치는 별도 유지(행 손실 금지)"


def test_non_consecutive_pages_not_merged():
    g1 = [["산업명", "지원금액"], ["자동차 부품", "5억원"]]
    g2 = [["산업명", "지원금액"], ["반도체 장비", "7억원"]]
    merged = merge_cross_page([(2, _region(g1)), (5, _region(g2))])  # 2 → 5 비연속
    assert len(merged) == 2
