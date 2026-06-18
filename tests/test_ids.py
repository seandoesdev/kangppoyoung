"""결정적 식별자 테스트 (설계 §13). 동일 입력 → 동일 ID, float 미세변동에 ID 불변."""
from __future__ import annotations

from pipeline import ids as I


def test_make_document_id_is_content_addressed():
    b = b"%PDF-1.7 sample bytes"
    assert I.make_document_id(b) == I.make_document_id(b)
    assert I.make_document_id(b).startswith("d_")
    assert len(I.make_document_id(b)) == 2 + 64  # "d_" + sha256 hex
    assert I.make_document_id(b) != I.make_document_id(b + b"x")


def test_norm_float_rounds_to_tenths():
    assert I.norm_float(72.04) == "72.0"
    assert I.norm_float(72.0) == "72.0"
    assert I.norm_float(519.96) == "520.0"


def test_norm_float_stable_against_patch_version_jitter():
    # PyMuPDF/pdfplumber 패치 버전 차이로 생기는 부동소수 미세변동이 ID를 흔들면 안 된다(§13.2).
    assert I.norm_float(72.00001) == I.norm_float(72.0) == "72.0"
    assert I.norm_float(100.019) == I.norm_float(99.981) == "100.0"


def test_norm_text_nfc_and_whitespace():
    assert I.norm_text("  정책자금   지원  ") == "정책자금 지원"
    # NFC 정규화: 분해형(자모 결합) 입력도 완성형과 동치가 된다
    assert I.norm_text("가") == I.norm_text("가") == "가"


def test_page_anchor():
    assert I.page_anchor(12, None) == "p12"
    assert I.page_anchor(None, (12, 13)) == "p12-13"


def test_make_chunk_id_deterministic_and_seq_sensitive():
    args = ("d_x", "text", "p1", "제1장", "정책자금 지원", 0)
    a = I.make_chunk_id(*args)
    assert a == I.make_chunk_id(*args)        # 동일 입력 → 동일 ID
    assert a.startswith("c_") and len(a) == 2 + 24
    # seq만 달라도 ID가 갈린다(형제 청크 충돌 방지)
    assert a != I.make_chunk_id("d_x", "text", "p1", "제1장", "정책자금 지원", 1)
    # 콘텐츠가 달라도 갈린다
    assert a != I.make_chunk_id("d_x", "text", "p1", "제1장", "다른 내용", 0)


def test_table_and_figure_ids_have_prefixes():
    assert I.make_table_id("d_x", "p2", "sig").startswith("tbl_")
    assert I.make_figure_id("d_x", "p3", "72.0|100.0").startswith("fig_")
    # 동일 서명이면 동일(분할표 논리 병합 전제)
    assert I.make_table_id("d_x", "p2", "sig") == I.make_table_id("d_x", "p2", "sig")
