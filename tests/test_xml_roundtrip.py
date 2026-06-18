"""XML 직렬화 round-trip + 안전성 테스트 (설계 §12). 모델 → XML → 모델 동치, 이스케이프, XXE 차단."""
from __future__ import annotations

from lxml import etree

from pipeline import serialize as S
from tests.conftest import make_text_chunk, make_table_row_chunk


def test_xml_roundtrip_preserves_text(doc_attrs):
    chunks = [make_text_chunk(), make_table_row_chunk("c_tbl_r1", "tbl_1", 1)]
    xml = S.to_chunks_xml(chunks, doc_attrs)
    reparsed = S.parse_chunks_xml(xml)
    assert len(reparsed) == len(chunks)
    assert {c.meta.chunk_id for c in reparsed} == {c.meta.chunk_id for c in chunks}
    orig = next(c for c in chunks if c.content.kind == "text")
    back = next(c for c in reparsed if c.meta.chunk_id == orig.meta.chunk_id)
    assert back.content.text == orig.content.text


def test_table_row_cols_survive_roundtrip(doc_attrs):
    ch = make_table_row_chunk("c_tbl_r1", "tbl_1", 1)
    xml = S.to_chunks_xml([ch], doc_attrs)
    back = S.parse_chunks_xml(xml)[0]
    assert back.content.kind == "table-row"
    assert {(c.name, c.value) for c in back.content.cols} == {("산업명", "자동차 부품 제조업"), ("지원금액", "5억원")}
    assert back.content.embedding_text == ch.content.embedding_text


def test_special_chars_are_escaped(doc_attrs):
    # &, <, >, " 가 깨지지 않고 round-trip(문자열 조립 금지 → 자동 이스케이프).
    ch = make_text_chunk(text='5 < 10 & "조건" > 기준')
    xml = S.to_chunks_xml([ch], doc_attrs)
    assert b"&amp;" in xml and b"&lt;" in xml  # 원시 &,< 가 아니라 엔티티로 기록
    back = S.parse_chunks_xml(xml)[0]
    assert back.content.text == '5 < 10 & "조건" > 기준'


def test_parser_blocks_external_entities():
    # XXE: 외부 엔티티 참조가 확장되지 않아야 한다(secure parser, §21).
    malicious = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b'<document><chunk id="c1"><meta/><content><text>&x;</text></content></chunk></document>'
    )
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(malicious, parser=parser)
    txt = root.find(".//text")
    # 엔티티가 파일 내용으로 확장되지 않음(빈/미해석)
    assert not (txt.text or "")


def test_xml_is_well_formed(doc_attrs):
    xml = S.to_chunks_xml([make_text_chunk()], doc_attrs)
    root = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
    assert root.tag == "document"
    assert root.get("generated_at") == doc_attrs["generated_at"]


def test_jsonl_parity_with_chunks():
    chunks = [make_text_chunk(), make_table_row_chunk("c_tbl_r1", "tbl_1", 1)]
    records, skipped = S.to_vector_records(chunks)
    ids = {c.meta.chunk_id for c in chunks}
    covered = {r["chunk_id"] for r in records} | set(skipped)
    assert covered == ids  # 모든 청크가 적재 또는 skip 으로 분류
    for r in records:
        assert r["embedding_text"].strip()           # 빈 embedding_text 는 적재 금지
        assert r["metadata"]["chunk_id"] == r["chunk_id"]
