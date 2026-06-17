"""산출물 직렬화 (설계 §12). 원본 XML(chunks.xml) + 검색 JSONL(chunks.jsonl) + manifest.

XML은 lxml el.text/el.set로만 주입(자동 이스케이프). 파싱은 secure parser(XXE 차단).
round-trip(역파싱)으로 텍스트 보존을 검증한다.
"""
from __future__ import annotations

import json
import os
import tempfile

from lxml import etree

from . import models as M
from .embedding import embedding_text


# ─────────────────────────── 직렬화 (모델 → XML) ───────────────────────────
def _sub(parent, tag, text=None, **attrs):
    el = etree.SubElement(parent, tag)
    for k, v in attrs.items():
        if v is not None:
            el.set(k.replace("_", "-"), str(v))
    if text is not None:
        el.text = str(text)
    return el


def _meta_to_xml(parent, m: M.Meta):
    me = etree.SubElement(parent, "meta")
    _sub(me, "chunk_id", m.chunk_id)
    _sub(me, "document_id", m.document_id)
    _sub(me, "file_name", m.file_name)
    if m.page_no is not None:
        _sub(me, "page_no", m.page_no)
    if m.page_range is not None:
        pr = etree.SubElement(me, "page_range")
        for p in m.page_range:
            _sub(pr, "p", p)
    _sub(me, "content_type", m.content_type.value)
    for tag in ("chapter", "section", "subsection", "item"):
        v = getattr(m, tag)
        if v is not None:
            _sub(me, tag, v)
    hp = etree.SubElement(me, "heading_path")
    for h in m.heading_path:
        _sub(hp, "h", h)
    if m.table_id:
        _sub(me, "table_id", m.table_id)
    if m.figure_id:
        _sub(me, "figure_id", m.figure_id)
    _sub(me, "extract_method", m.extract_method.value)
    _sub(me, "confidence", f"{m.confidence:.3f}")
    if m.bbox is not None:
        _sub(me, "bbox", page=m.bbox.page, x0=f"{m.bbox.x0:.1f}", y0=f"{m.bbox.y0:.1f}",
             x1=f"{m.bbox.x1:.1f}", y1=f"{m.bbox.y1:.1f}")
    for tag in ("parent_chunk_id", "previous_chunk_id", "next_chunk_id"):
        v = getattr(m, tag)
        if v is not None:
            _sub(me, tag, v)
    rc = etree.SubElement(me, "related_chunk_ids")
    for rid in m.related_chunk_ids:
        _sub(rc, "id", rid)
    _sub(me, "needs_review", "true" if m.needs_review else "false")
    rr = etree.SubElement(me, "review_reasons")
    for r in m.review_reasons:
        _sub(rr, "r", r)
    _sub(me, "source_location", locator=m.source_location.locator)
    return me


def _content_to_xml(parent, c: M.Content):
    ce = etree.SubElement(parent, "content")
    k = c.kind
    if k == "text":
        _sub(ce, "text", c.text)
    elif k == "list-item":
        _sub(ce, "list-item", c.text, marker=c.marker)
    elif k == "table-row":
        tr = etree.SubElement(ce, "table-row")
        if c.section_path:
            sp = etree.SubElement(tr, "section-path")
            for s in c.section_path:
                _sub(sp, "s", s)
        for col in c.cols:
            _sub(tr, "col", col.value, name=col.name)
        _sub(tr, "embedding_text", c.embedding_text)
    elif k == "table-note":
        _sub(ce, "table-note", c.text)
    elif k == "warning":
        _sub(ce, "warning", c.text, level=c.level)
    elif k == "footnote":
        _sub(ce, "footnote", c.text, ref_marker=c.ref_marker)
    elif k == "reference":
        _sub(ce, "reference", c.text, target_hint=c.target_hint)
    elif k == "infographic":
        ig = etree.SubElement(ce, "infographic")
        if c.info_kind:
            ig.set("kind", c.info_kind)
        _sub(ig, "summary", c.summary)
        if c.reading:
            _sub(ig, "reading", c.reading)
        for d in c.data_points:
            _sub(ig, "data-point", d.value, name=d.name)
        if c.ocr_text:
            _sub(ig, "ocr-text", c.ocr_text)
    else:
        raise NotImplementedError(f"XML 직렬화 미지원 content_type: {k}")
    return ce


def to_chunks_xml(chunks: list[M.Chunk], doc_attrs: dict) -> bytes:
    root = etree.Element("document")
    for k, v in doc_attrs.items():
        root.set(k, str(v))
    for ch in chunks:
        ce = etree.SubElement(root, "chunk")
        ce.set("id", ch.meta.chunk_id)
        _meta_to_xml(ce, ch.meta)
        _content_to_xml(ce, ch.content)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ─────────────────────────── 역파싱 (XML → 모델) : round-trip 검증용 ───────────────────────────
def _secure_parser():
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


def _txt(el, tag):
    c = el.find(tag)
    return c.text if c is not None else None


def _xml_to_meta(me) -> dict:
    d: dict = {}
    d["chunk_id"] = _txt(me, "chunk_id")
    d["document_id"] = _txt(me, "document_id")
    d["file_name"] = _txt(me, "file_name")
    if me.find("page_no") is not None:
        d["page_no"] = int(_txt(me, "page_no"))
    pr = me.find("page_range")
    if pr is not None:
        ps = [int(p.text) for p in pr.findall("p")]
        d["page_range"] = (ps[0], ps[1])
    d["content_type"] = _txt(me, "content_type")
    for tag in ("chapter", "section", "subsection", "item"):
        if me.find(tag) is not None:
            d[tag] = _txt(me, tag)
    hp = me.find("heading_path")
    d["heading_path"] = [h.text for h in hp.findall("h")] if hp is not None else []
    if me.find("table_id") is not None:
        d["table_id"] = _txt(me, "table_id")
    if me.find("figure_id") is not None:
        d["figure_id"] = _txt(me, "figure_id")
    d["extract_method"] = _txt(me, "extract_method")
    d["confidence"] = float(_txt(me, "confidence"))
    bb = me.find("bbox")
    if bb is not None:
        d["bbox"] = {"page": int(bb.get("page")), "x0": float(bb.get("x0")),
                     "y0": float(bb.get("y0")), "x1": float(bb.get("x1")), "y1": float(bb.get("y1"))}
    for tag in ("parent_chunk_id", "previous_chunk_id", "next_chunk_id"):
        if me.find(tag) is not None:
            d[tag] = _txt(me, tag)
    rc = me.find("related_chunk_ids")
    d["related_chunk_ids"] = [i.text for i in rc.findall("id")] if rc is not None else []
    d["needs_review"] = (_txt(me, "needs_review") == "true")
    rr = me.find("review_reasons")
    d["review_reasons"] = [r.text for r in rr.findall("r")] if rr is not None else []
    sl = me.find("source_location")
    d["source_location"] = {
        "file_name": d["file_name"], "document_id": d["document_id"],
        "page_no": d.get("page_no"), "page_range": d.get("page_range"),
        "bbox": d.get("bbox"), "extract_method": d["extract_method"],
        "heading_path": d["heading_path"],
        "locator": sl.get("locator") if sl is not None else None,
        "table_id": d.get("table_id"), "figure_id": d.get("figure_id"),
    }
    return d


def _xml_to_content(ce) -> dict:
    el = ce[0]
    tag = el.tag
    if tag == "text":
        return {"kind": "text", "text": el.text or ""}
    if tag == "list-item":
        return {"kind": "list-item", "marker": el.get("marker"), "text": el.text or ""}
    if tag == "table-row":
        sp = el.find("section-path")
        section_path = [s.text for s in sp.findall("s")] if sp is not None else []
        cols = [{"name": c.get("name"), "value": c.text or ""} for c in el.findall("col")]
        return {"kind": "table-row", "cols": cols, "section_path": section_path,
                "embedding_text": _txt(el, "embedding_text") or ""}
    if tag == "table-note":
        return {"kind": "table-note", "text": el.text or ""}
    if tag == "warning":
        return {"kind": "warning", "level": el.get("level"), "text": el.text or ""}
    if tag == "footnote":
        return {"kind": "footnote", "ref_marker": el.get("ref-marker"), "text": el.text or ""}
    if tag == "reference":
        return {"kind": "reference", "target_hint": el.get("target-hint"), "text": el.text or ""}
    if tag == "infographic":
        dps = [{"name": d.get("name"), "value": d.text or ""} for d in el.findall("data-point")]
        return {"kind": "infographic", "info_kind": el.get("kind"),
                "summary": _txt(el, "summary") or "", "reading": _txt(el, "reading"),
                "data_points": dps, "ocr_text": _txt(el, "ocr-text")}
    raise NotImplementedError(f"XML 역파싱 미지원: {tag}")


def parse_chunks_xml(data: bytes) -> list[M.Chunk]:
    root = etree.fromstring(data, parser=_secure_parser())
    out = []
    for ce in root.findall("chunk"):
        meta = _xml_to_meta(ce.find("meta"))
        content = _xml_to_content(ce.find("content"))
        out.append(M.Chunk(meta=meta, content=content))
    return out


# ─────────────────────────── JSONL (검색용) ───────────────────────────
def to_vector_records(chunks: list[M.Chunk]) -> tuple[list[dict], list[str]]:
    recs, skipped = [], []
    for ch in chunks:
        et = embedding_text(ch).strip()
        if not et:
            skipped.append(ch.meta.chunk_id)
            continue
        recs.append({
            "chunk_id": ch.meta.chunk_id,
            "document_id": ch.meta.document_id,
            "content_type": ch.meta.content_type.value,
            "embedding_text": et,
            "metadata": ch.meta.model_dump(mode="json"),
        })
    return recs, skipped


# ─────────────────────────── 원자적 쓰기 ───────────────────────────
def _atomic_write(path: str, data: bytes):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_xml(path: str, chunks: list[M.Chunk], doc_attrs: dict):
    _atomic_write(path, to_chunks_xml(chunks, doc_attrs))


def write_jsonl(path: str, records: list[dict]):
    buf = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    _atomic_write(path, (buf + ("\n" if buf else "")).encode("utf-8"))


def write_manifest(path: str, manifest: dict):
    _atomic_write(path, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
