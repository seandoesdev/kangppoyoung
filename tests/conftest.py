"""공용 픽스처. 단위 테스트는 합성 Chunk/grid로, 통합 테스트는 source/ 실제 PDF로 검증한다."""
from __future__ import annotations

import glob
import os

import pytest

from pipeline import models as M

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_text_chunk(
    chunk_id: str = "c_text_0001",
    text: str = "정책자금 신청은 온라인으로 접수한다.",
    page_no: int = 1,
    heading_path: list[str] | None = None,
    content_type: M.ContentType = M.ContentType.TEXT,
) -> M.Chunk:
    """검증 가능한 최소 text 청크. SourceLocation/bbox 불변식을 모두 만족한다."""
    hp = heading_path or ["제1장", "1절"]
    bbox = M.BBox(page=page_no, x0=72.0, y0=100.0, x1=520.0, y1=130.0)
    sl = M.SourceLocation(
        file_name="sample.pdf", document_id="d_" + "a" * 64, page_no=page_no,
        bbox=bbox, extract_method=M.ExtractMethod.PDF_TEXT, heading_path=hp,
        locator=" > ".join(hp),
    )
    meta = M.Meta(
        chunk_id=chunk_id, document_id="d_" + "a" * 64, file_name="sample.pdf",
        page_no=page_no, content_type=content_type,
        heading_path=hp, extract_method=M.ExtractMethod.PDF_TEXT,
        confidence=0.95, bbox=bbox, source_location=sl,
    )
    return M.Chunk(meta=meta, content=M.TextContent(text=text))


def make_table_row_chunk(chunk_id: str, table_id: str, seq: int) -> M.Chunk:
    bbox = M.BBox(page=2, x0=72.0, y0=200.0 + seq, x1=520.0, y1=230.0 + seq)
    sl = M.SourceLocation(
        file_name="sample.pdf", document_id="d_" + "a" * 64, page_no=2,
        bbox=bbox, extract_method=M.ExtractMethod.PDF_TEXT, table_id=table_id,
    )
    meta = M.Meta(
        chunk_id=chunk_id, document_id="d_" + "a" * 64, file_name="sample.pdf",
        page_no=2, content_type=M.ContentType.TABLE_ROW, table_id=table_id,
        extract_method=M.ExtractMethod.PDF_TEXT, confidence=0.94, bbox=bbox,
        source_location=sl,
    )
    content = M.TableRowContent(
        cols=[M.Col(name="산업명", value="자동차 부품 제조업"), M.Col(name="지원금액", value="5억원")],
        embedding_text="자동차 부품 제조업 지원금액 5억원",
    )
    return M.Chunk(meta=meta, content=content)


def make_table_note_chunk(chunk_id: str, table_id: str, text: str = "표 주석") -> M.Chunk:
    bbox = M.BBox(page=2, x0=72.0, y0=300.0, x1=520.0, y1=320.0)
    sl = M.SourceLocation(
        file_name="sample.pdf", document_id="d_" + "a" * 64, page_no=2,
        bbox=bbox, extract_method=M.ExtractMethod.PDF_TEXT, table_id=table_id,
    )
    meta = M.Meta(
        chunk_id=chunk_id, document_id="d_" + "a" * 64, file_name="sample.pdf",
        page_no=2, content_type=M.ContentType.TABLE_NOTE, table_id=table_id,
        extract_method=M.ExtractMethod.PDF_TEXT, confidence=0.9, bbox=bbox, source_location=sl,
    )
    return M.Chunk(meta=meta, content=M.TableNoteContent(text=text))


def make_figure_chunk(chunk_id: str, figure_id: str, seq: int = 0) -> M.Chunk:
    bbox = M.BBox(page=3, x0=72.0, y0=100.0 + seq, x1=272.0, y1=300.0 + seq)
    sl = M.SourceLocation(
        file_name="sample.pdf", document_id="d_" + "a" * 64, page_no=3,
        bbox=bbox, extract_method=M.ExtractMethod.LAYOUT_ANALYSIS, figure_id=figure_id,
    )
    meta = M.Meta(
        chunk_id=chunk_id, document_id="d_" + "a" * 64, file_name="sample.pdf",
        page_no=3, content_type=M.ContentType.INFOGRAPHIC, figure_id=figure_id,
        extract_method=M.ExtractMethod.LAYOUT_ANALYSIS, confidence=0.3, bbox=bbox, source_location=sl,
    )
    return M.Chunk(meta=meta, content=M.InfographicContent(summary="그림 설명"))


@pytest.fixture
def text_chunk() -> M.Chunk:
    return make_text_chunk()


@pytest.fixture
def doc_attrs() -> dict:
    return {
        "id": "d_" + "a" * 64, "file_name": "sample.pdf",
        "source_sha256": "a" * 64, "pipeline_version": "1.0.0",
        "generated_at": "2026-01-01T00:00:00+00:00",
    }


@pytest.fixture(scope="session")
def sample_pdf() -> str:
    """source/ 의 가장 작은 실제 PDF(기초 가이드). 없으면 통합 테스트 skip."""
    matches = glob.glob(os.path.join(REPO_ROOT, "source", "3.*.pdf"))
    if not matches:
        pytest.skip("source/3.*.pdf 없음 — 통합 테스트 건너뜀")
    return matches[0]
