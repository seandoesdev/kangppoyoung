"""모델 계약 테스트 (설계 §11). validator·discriminated union·json-schema export·round-trip."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline import models as M
from tests.conftest import make_text_chunk


def test_chunk_round_trips_through_model_dump():
    ch = make_text_chunk()
    dumped = ch.model_dump(mode="json")
    restored = M.Chunk.model_validate(dumped)
    assert restored == ch


def test_json_schema_export_handles_discriminated_union():
    # 중첩 discriminated-union(Content)이 json-schema export에서 깨지지 않아야 한다(§11.3).
    schema = M.Chunk.model_json_schema()
    assert "properties" in schema and "content" in schema["properties"]


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        M.BBox(page=1, x0=0.0, y0=0.0, x1=1.0, y1=1.0, bogus=123)


def test_source_location_requires_bbox_or_char_range():
    with pytest.raises(ValidationError, match="bbox 또는 char_range"):
        M.SourceLocation(
            file_name="x.pdf", document_id="d_x",
            extract_method=M.ExtractMethod.PDF_TEXT,
        )


def test_meta_requires_page_no_or_page_range():
    bbox = M.BBox(page=1, x0=0.0, y0=0.0, x1=1.0, y1=1.0)
    sl = M.SourceLocation(file_name="x.pdf", document_id="d_x", bbox=bbox,
                          extract_method=M.ExtractMethod.PDF_TEXT)
    with pytest.raises(ValidationError, match="page_no 또는 page_range"):
        M.Meta(chunk_id="c1", document_id="d_x", file_name="x.pdf",
               content_type=M.ContentType.TEXT, extract_method=M.ExtractMethod.PDF_TEXT,
               confidence=0.9, bbox=bbox, source_location=sl)


def test_table_row_requires_table_id():
    bbox = M.BBox(page=1, x0=0.0, y0=0.0, x1=1.0, y1=1.0)
    sl = M.SourceLocation(file_name="x.pdf", document_id="d_x", page_no=1, bbox=bbox,
                          extract_method=M.ExtractMethod.PDF_TEXT)
    with pytest.raises(ValidationError, match="table_id 필수"):
        M.Meta(chunk_id="c1", document_id="d_x", file_name="x.pdf", page_no=1,
               content_type=M.ContentType.TABLE_ROW, extract_method=M.ExtractMethod.PDF_TEXT,
               confidence=0.9, bbox=bbox, source_location=sl)


def test_chunk_type_alignment_enforced():
    # meta.content_type 와 content.kind 가 어긋나면 거부(§11.3 discriminator 1:1).
    ch = make_text_chunk()
    bad_meta = ch.meta.model_copy(update={"content_type": M.ContentType.WARNING})
    with pytest.raises(ValidationError, match="content_type"):
        M.Chunk(meta=bad_meta, content=M.TextContent(text="x"))


def test_confidence_out_of_bounds_rejected():
    ch = make_text_chunk()
    meta_dict = ch.meta.model_dump() | {"confidence": 1.5}
    with pytest.raises(ValidationError):
        M.Meta.model_validate(meta_dict)
