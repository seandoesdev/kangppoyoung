"""CLI 계약 통합 테스트 (설계 §16). 실제 PDF로 종료코드·산출물·manifest·검증을 확인한다."""
from __future__ import annotations

import json

from pipeline.cli import main

FIXED_TS = "2026-01-01T00:00:00+00:00"


def _run(pdf, outdir):
    return main(["--input", pdf, "--outdir", str(outdir), "--generated-at", FIXED_TS])


def test_cli_success_produces_all_outputs(sample_pdf, tmp_path, capsys):
    code = _run(sample_pdf, tmp_path)
    assert code == 0
    for name in ("chunks.xml", "chunks.jsonl", "manifest.json"):
        assert (tmp_path / name).is_file(), f"{name} 누락"

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "ok"
    assert manifest["counts"]["chunks"] > 0
    assert manifest["verification"]["passed"] is True
    # 텍스트 보존 무손실 게이트(주지표 char_recall ≥ 0.99)
    assert manifest["verification"]["metrics"]["char_recall"] >= 0.99


def test_cli_stdout_last_line_is_sentinel_manifest(sample_pdf, tmp_path, capsys):
    _run(sample_pdf, tmp_path)
    out_lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    last = json.loads(out_lines[-1])
    assert last.get("@@MANIFEST@@") is True            # Spring 파싱용 센티넬(§16.1)


def test_cli_jsonl_is_valid_and_has_source_tail(sample_pdf, tmp_path, capsys):
    _run(sample_pdf, tmp_path)
    lines = (tmp_path / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    rec = json.loads(lines[0])
    assert {"chunk_id", "content_type", "embedding_text", "metadata"} <= rec.keys()
    assert "(출처:" in rec["embedding_text"]            # 출처 꼬리표 항상 부착(§12.2)


def test_cli_missing_input_returns_exit_3(tmp_path, capsys):
    code = main(["--input", str(tmp_path / "nope.pdf"), "--outdir", str(tmp_path / "o")])
    assert code == 3
    last = json.loads([l for l in capsys.readouterr().out.splitlines() if l.strip()][-1])
    assert last["status"] == "error" and last["exit_code"] == 3
