"""검증 (설계 §12 round-trip + 텍스트 보존). 원본 PDF ↔ 변환 산출물의 정확성을 측정한다.

검사: ①텍스트 보존율(원문 문자 bigram이 산출 청크에 남았는가) ②XML↔JSONL chunk_id parity
③XML round-trip(역파싱 텍스트 동치) ④관계 무결성(dangling) ⑤chunk_id 유일성.
"""
from __future__ import annotations

import collections
import re
import unicodedata

import pdfplumber

from . import models as M
from .serialize import parse_chunks_xml

_WORDISH = re.compile(r"[가-힣A-Za-z0-9]")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", "".join((s or "").split()))


def _words(s: str) -> list[str]:
    """단어 토큰(한글/영숫자 포함만). 점선 리더(······)·순수 기호 토큰은 보존율 분모에서 제외."""
    toks = unicodedata.normalize("NFC", s or "").replace("\n", " ").split()
    return [t for t in toks if _WORDISH.search(t)]


def _word_recall(original: str, output: str) -> float:
    orig = collections.Counter(_words(original))
    out = collections.Counter(_words(output))
    total = sum(orig.values())
    if not total:
        return 1.0
    hit = sum(min(c, out[w]) for w, c in orig.items())
    return hit / total


def _chars(s: str) -> list[str]:
    return [c for c in unicodedata.normalize("NFC", s or "") if _WORDISH.match(c)]


def _char_recall(original: str, output: str) -> tuple[float, int]:
    """문자 다중집합 recall(토큰화·재정렬에 불변). '원문 글자가 산출에 남았는가'의 무손실 지표."""
    orig = collections.Counter(_chars(original))
    out = collections.Counter(_chars(output))
    total = sum(orig.values())
    if not total:
        return 1.0, 0
    hit = sum(min(c, out[ch]) for ch, c in orig.items())
    return hit / total, total - hit


def _bigrams(s: str) -> set[str]:
    s = _norm(s)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _chunk_text_parts(ch: M.Chunk) -> list[str]:
    c = ch.content
    parts: list[str] = list(ch.meta.heading_path)
    k = c.kind
    if k in ("text", "warning", "footnote", "reference", "table-note"):
        parts.append(c.text)
    elif k == "list-item":
        if c.marker:
            parts.append(c.marker)
        parts.append(c.text)
    elif k == "table-row":
        parts.extend(c.section_path)
        for col in c.cols:
            parts.append(col.value)
            parts.append(col.name.replace("_", " "))
    # infographic(placeholder)은 원문 텍스트가 아니므로 보존율 계산에서 제외
    return parts


def _original_text(pdf_path: str) -> str:
    buf = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            buf.append(page.extract_text() or "")
    return "\n".join(buf)


def verify_document(
    pdf_path: str, chunks: list[M.Chunk], xml_bytes: bytes,
    jsonl_ids: list[str], skipped_ids: list[str],
) -> dict:
    rep: dict = {"checks": {}, "metrics": {}, "issues": []}
    ids = [ch.meta.chunk_id for ch in chunks]
    idset = set(ids)

    # ① 텍스트 보존율: 문자 다중집합 recall(주지표, 무손실)을 게이트로 쓴다. 토큰화·재정렬에
    # 불변이라 "원문 글자가 산출에 남았는가"를 정확히 측정한다. 단어 recall은 보조 신호로 보고
    # (pdfplumber가 인접 단어를 붙여 토큰화하는 등 경계 차이에 민감).
    original = _original_text(pdf_path)
    out_text = " ".join(p for ch in chunks for p in _chunk_text_parts(ch))
    char_recall, char_missing = _char_recall(original, out_text)
    word_recall = _word_recall(original, out_text)
    rep["metrics"]["char_recall"] = round(char_recall, 4)
    rep["metrics"]["text_coverage"] = round(char_recall, 4)   # 주지표(무손실)
    rep["metrics"]["word_recall"] = round(word_recall, 4)
    rep["metrics"]["chars_missing"] = char_missing
    rep["metrics"]["orig_chars"] = len(_chars(original))
    rep["checks"]["text_coverage_ok"] = char_recall >= 0.99

    # ② chunk_id 유일성
    dup = len(ids) - len(idset)
    rep["checks"]["chunk_id_unique"] = dup == 0
    if dup:
        rep["issues"].append(f"중복 chunk_id {dup}건")

    # ③ XML ↔ JSONL parity
    xml_ids = {ch.meta.chunk_id for ch in parse_chunks_xml(xml_bytes)}
    jset = set(jsonl_ids)
    parity = (xml_ids == idset) and jset.issubset(idset) and (jset | set(skipped_ids) == idset)
    rep["checks"]["xml_jsonl_parity"] = parity
    if xml_ids != idset:
        rep["issues"].append(f"XML/모델 id 불일치: xml-only {len(xml_ids - idset)}, model-only {len(idset - xml_ids)}")
    if not (jset | set(skipped_ids) == idset):
        rep["issues"].append("JSONL(+skipped)이 전체 chunk_id를 덮지 못함")

    # ④ XML round-trip (역파싱 텍스트 동치)
    reparsed = parse_chunks_xml(xml_bytes)
    rt_ok = len(reparsed) == len(chunks)
    mism = 0
    orig_by_id = {ch.meta.chunk_id: ch for ch in chunks}
    for rc in reparsed:
        oc = orig_by_id.get(rc.meta.chunk_id)
        if oc is None:
            rt_ok = False
            continue
        if _norm(" ".join(_chunk_text_parts(rc))) != _norm(" ".join(_chunk_text_parts(oc))):
            mism += 1
    rep["checks"]["xml_roundtrip"] = rt_ok and mism == 0
    if mism:
        rep["issues"].append(f"round-trip 텍스트 불일치 {mism}건")

    # ⑤ 관계 무결성 (dangling 참조)
    dangling = 0
    for ch in chunks:
        m = ch.meta
        refs = [m.parent_chunk_id, m.previous_chunk_id, m.next_chunk_id] + list(m.related_chunk_ids)
        for r in refs:
            if r is not None and r not in idset:
                dangling += 1
    rep["checks"]["relations_intact"] = dangling == 0
    if dangling:
        rep["issues"].append(f"dangling 관계 참조 {dangling}건")

    rep["passed"] = all(rep["checks"].values())
    return rep
