"""표 Row 정규화 테스트 (설계 §7). 헤더 인식·컬럼명·세로병합 채움·섹션 상속·embedding·무손실 폴백."""
from __future__ import annotations

from pipeline.config import Config
from pipeline.extract import TableRegion
from pipeline.tables import build_table_chunks


def _tok(*rows):
    out = []
    for r in rows:
        for c in r:
            out.extend(str(c).split())
    return out


def _region(grid, words=None):
    nrows = len(grid)
    rbb = [(72.0, 100.0 + 20 * i, 520.0, 118.0 + 20 * i) for i in range(nrows)]
    return TableRegion(
        x0=72.0, y0=100.0, x1=520.0, y1=100.0 + 20 * nrows,
        grid=grid, row_bboxes=rbb, words=words if words is not None else _tok(*grid),
    )


def test_rows_become_chunks_with_named_cols():
    grid = [
        ["산업분류코드", "산업명", "지원금액"],
        ["1234", "자동차 부품 제조업", "5억원"],
        ["5678", "조선해양 기자재", "3억원"],
    ]
    rows = build_table_chunks(_region(grid), page_no=2, heading_path=["제2장"], document_id="d_x", cfg=Config())
    assert len(rows) == 2
    assert all(r.content_type == "table-row" for r in rows)
    first = dict(rows[0].cols)
    assert first["산업명"] == "자동차 부품 제조업"
    assert first["지원금액"] == "5억원"
    # embedding_core 는 컬럼 의미를 포함
    assert "자동차 부품 제조업" in rows[0].embedding_core


def test_all_rows_share_one_table_id():
    grid = [["A", "B"], ["1", "2"], ["3", "4"]]
    rows = build_table_chunks(_region(grid), 2, ["제2장"], "d_x", Config())
    ids = {r.table_id for r in rows}
    assert len(ids) == 1 and next(iter(ids)).startswith("tbl_")


def test_section_row_is_inherited_not_emitted():
    grid = [
        ["구분", "금액"],
        ["1. 제조업 분야", ""],   # 첫 칸만 채워진 섹션 행 → 상속 라벨(레코드 아님)
        ["운전자금", "5억원"],
        ["시설자금", "10억원"],
    ]
    rows = build_table_chunks(_region(grid), 2, ["제2장"], "d_x", Config())
    # 섹션 행은 레코드로 나오지 않는다 → 데이터 행 2개만
    assert len(rows) == 2
    assert all(r.section_path == ["1. 제조업 분야"] for r in rows)
    assert "1. 제조업 분야" in rows[0].embedding_core


def test_rows_inherit_heading_section_when_no_in_table_section():
    """표 내부 섹션 행이 없으면 각 Row는 표 위치의 heading_path를 section_path로 상속한다(§7)."""
    grid = [
        ["산업명", "지원금액"],
        ["자동차 부품", "5억원"],
        ["조선 기자재", "3억원"],
    ]
    rows = build_table_chunks(_region(grid), 2, ["제2장", "지원대상"], "d_x", Config())
    assert len(rows) == 2
    assert all(r.section_path == ["제2장", "지원대상"] for r in rows)
    assert "지원대상" in rows[0].embedding_core


def test_in_table_section_row_takes_precedence_over_heading():
    """표 내부 섹션 행이 있으면 그 라벨이 section_path가 된다(기존 동작 보존)."""
    grid = [
        ["구분", "금액"],
        ["1. 제조업 분야", ""],
        ["운전자금", "5억원"],
    ]
    rows = build_table_chunks(_region(grid), 2, ["제2장"], "d_x", Config())
    assert rows[0].section_path == ["1. 제조업 분야"]


def test_vertical_merge_fill_down():
    grid = [
        ["대분류", "세부", "금액"],
        ["제조업", "운전자금", "5억원"],
        ["", "시설자금", "10억원"],   # 대분류 빈칸 → 위 값 상속
    ]
    rows = build_table_chunks(_region(grid), 2, ["제2장"], "d_x", Config())
    assert len(rows) == 2
    assert dict(rows[1].cols)["대분류"] == "제조업"   # 세로 병합 채움


def test_lossy_extraction_falls_back_to_text():
    # 구조화한 셀이 영역 원문 단어를 충분히 못 담으면 text 폴백(무손실 보장, table_fallback).
    grid = [["A", "B"], ["1", "2"]]
    extra_words = ["설명", "문단", "각주", "텍스트", "추가", "누락", "방지", "보존"] * 3
    rows = build_table_chunks(_region(grid, words=extra_words), 2, ["제2장"], "d_x", Config())
    assert rows, "폴백은 최소 1개 text 청크를 내야 한다"
    assert all(r.content_type == "text" for r in rows)
    assert all("table_fallback" in r.review_reasons for r in rows)
