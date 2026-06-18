"""결정성·멱등 회귀 (설계 §13, §21). 동일 입력 + 고정 generated_at → byte-동일 XML/JSONL.

OCR/Vision 경로는 환경 의존이라 제외하고, offline pdf_text/규칙/직렬화 경로만 byte-동일 회귀한다(§13.2).
"""
from __future__ import annotations

import hashlib
import json

from pipeline.cli import main

FIXED_TS = "2026-01-01T00:00:00+00:00"


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(pdf, outdir):
    code = main(["--input", pdf, "--outdir", str(outdir), "--generated-at", FIXED_TS])
    assert code == 0
    return outdir


def _ids(outdir):
    return [json.loads(l)["chunk_id"]
            for l in (outdir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]


def test_xml_and_jsonl_are_byte_identical_across_runs(sample_pdf, tmp_path, capsys):
    a = _run(sample_pdf, tmp_path / "a")
    b = _run(sample_pdf, tmp_path / "b")
    assert _digest(a / "chunks.xml") == _digest(b / "chunks.xml"), "XML 비결정(설계 §13 위반)"
    assert _digest(a / "chunks.jsonl") == _digest(b / "chunks.jsonl"), "JSONL 비결정(설계 §13 위반)"


def test_chunk_ids_stable_across_runs(sample_pdf, tmp_path, capsys):
    a = _run(sample_pdf, tmp_path / "a")
    b = _run(sample_pdf, tmp_path / "b")
    ids_a, ids_b = _ids(a), _ids(b)
    assert ids_a == ids_b and ids_a, "chunk_id 가 재실행 간 흔들림(멱등 upsert 깨짐)"
