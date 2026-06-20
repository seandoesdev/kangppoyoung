"""CLI 진입점 (설계 §16). Spring이 ProcessBuilder로 실행한다.

사용: python -m pipeline --input <pdf> --outdir <dir> [--offline] [--no-verify]
출력: <outdir>/chunks.xml, chunks.jsonl, manifest.json. stdout 마지막 줄 = manifest(@@MANIFEST@@).
종료코드: 0 성공/부분성공, 2 인자오류, 3 입력오류, 4 검증실패, 5 한도초과, 1 내부오류.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import sys
import time
import traceback

from . import PIPELINE_VERSION
from .build import build_chunks
from .config import Config
from .serialize import to_chunks_xml, to_vector_records, write_jsonl, write_manifest, write_xml


def _resolve_generated_at(cli_value: str | None) -> str:
    """document/@generated_at 결정. 우선순위: --generated-at > SOURCE_DATE_EPOCH env > 현재 UTC.

    고정값을 주면 chunk 내용·ID와 무관한 유일한 비결정 요소(벽시계)를 제거해 XML이 byte-동일해진다
    (§13.2: generated_at는 XML 속성 전용, chunk_id 해시 미포함). 골든 회귀·재현 빌드에서 사용한다.
    """
    if cli_value:
        return cli_value
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc).isoformat()
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _emit_manifest(manifest: dict, outdir: str | None):
    line = json.dumps({"@@MANIFEST@@": True, **manifest}, ensure_ascii=False)
    print(line)
    if outdir:
        try:
            write_manifest(os.path.join(outdir, "manifest.json"), manifest)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline", description="PDF → RAG Chunk 변환")
    ap.add_argument("--input", required=True, help="입력 PDF 절대경로")
    ap.add_argument("--outdir", required=True, help="산출물 디렉터리")
    ap.add_argument("--doc-id", default=None, help="문서 ID(미지정 시 PDF 콘텐츠 해시)")
    ap.add_argument("--offline", action="store_true", default=True, help="Vision/OCR 미사용(기본)")
    ap.add_argument("--confidence-threshold", type=float, default=0.7)
    ap.add_argument("--table-confidence-threshold", type=float, default=0.6)
    ap.add_argument("--max-chunk-chars", type=int, default=800)
    ap.add_argument("--max-input-mb", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=300)
    ap.add_argument("--merge", action="store_true",
                    help="청크 품질 개선(병합) 스테이지 활성화(온라인, OPENAI_API_KEY 필요)")
    ap.add_argument("--merge-model", default="gpt-4o", help="병합 경계 판단 모델")
    ap.add_argument("--merge-cache", default=None, help="경계 결정 캐시 파일 경로(결정론 재현)")
    ap.add_argument("--no-verify", action="store_true", help="검증 단계 생략")
    ap.add_argument("--generated-at", default=None,
                    help="document/@generated_at 고정값(ISO-8601). 미지정 시 SOURCE_DATE_EPOCH "
                         "env, 그것도 없으면 현재 UTC. 골든 byte-동일 회귀용(§13.2).")
    args = ap.parse_args(argv)

    cfg = Config(
        confidence_threshold=args.confidence_threshold,
        table_confidence_threshold=args.table_confidence_threshold,
        max_chunk_chars=args.max_chunk_chars,
        max_input_mb=args.max_input_mb,
        max_pages=args.max_pages,
        merge_enabled=args.merge,
        merge_model=args.merge_model,
        merge_cache_path=args.merge_cache,
    )
    file_name = os.path.basename(args.input)

    # 입력 가드
    if not os.path.isfile(args.input):
        _emit_manifest({"status": "error", "exit_code": 3, "category": "input",
                        "message": "입력 파일을 찾을 수 없습니다", "file_name": file_name,
                        "pipeline_version": PIPELINE_VERSION}, None)
        return 3
    size_mb = os.path.getsize(args.input) / (1024 * 1024)
    if size_mb > cfg.max_input_mb:
        _emit_manifest({"status": "error", "exit_code": 3, "category": "input",
                        "message": f"입력이 너무 큼({size_mb:.1f}MB > {cfg.max_input_mb}MB)",
                        "file_name": file_name, "pipeline_version": PIPELINE_VERSION}, None)
        return 3

    os.makedirs(args.outdir, exist_ok=True)
    t = {}
    try:
        t0 = time.perf_counter()
        chunks, doc_info = build_chunks(args.input, cfg)
        t["build_ms"] = int((time.perf_counter() - t0) * 1000)

        if doc_info["pages"] > cfg.max_pages:
            _emit_manifest({"status": "error", "exit_code": 5, "category": "limit",
                            "message": f"페이지 한도 초과({doc_info['pages']}>{cfg.max_pages})",
                            "file_name": file_name, "pipeline_version": PIPELINE_VERSION}, args.outdir)
            return 5

        doc_id = args.doc_id or doc_info["document_id"]
        generated_at = _resolve_generated_at(args.generated_at)
        doc_attrs = {"id": doc_id, "file_name": file_name,
                     "source_sha256": doc_info["source_sha256"],
                     "pipeline_version": PIPELINE_VERSION, "generated_at": generated_at}

        t1 = time.perf_counter()
        xml_bytes = to_chunks_xml(chunks, doc_attrs)
        records, skipped = to_vector_records(chunks)
        xml_path = os.path.join(args.outdir, "chunks.xml")
        jsonl_path = os.path.join(args.outdir, "chunks.jsonl")
        write_xml(xml_path, chunks, doc_attrs)
        write_jsonl(jsonl_path, records)
        t["serialize_ms"] = int((time.perf_counter() - t1) * 1000)

        by_type = collections.Counter(ch.meta.content_type.value for ch in chunks)
        by_method = collections.Counter(ch.meta.extract_method.value for ch in chunks)
        review = [ch.meta.chunk_id for ch in chunks if ch.meta.needs_review]
        reasons = collections.Counter(r for ch in chunks for r in ch.meta.review_reasons)

        manifest = {
            "status": "ok", "document_id": doc_id, "source_sha256": doc_info["source_sha256"],
            "file_name": file_name, "pipeline_version": PIPELINE_VERSION,
            "counts": {"chunks": len(chunks), "by_type": dict(by_type),
                       "pages": doc_info["pages"], "scanned_pages": doc_info["scanned_pages"]},
            "extract_methods": dict(by_method),
            "outputs": {"xml": os.path.abspath(xml_path), "jsonl": os.path.abspath(jsonl_path),
                        "manifest": os.path.abspath(os.path.join(args.outdir, "manifest.json"))},
            "review_required": {"count": len(review), "reasons": dict(reasons),
                                "chunk_ids": review[:50]},
            "jsonl_skipped": len(skipped),
            "offline": True, "provider": "offline", "timings_ms": t,
            "merge": {"enabled": cfg.merge_enabled,
                      "model": cfg.merge_model if cfg.merge_enabled else None},
        }

        # 검증
        if not args.no_verify:
            from .verify import verify_document
            t2 = time.perf_counter()
            rep = verify_document(args.input, chunks, xml_bytes, [r["chunk_id"] for r in records], skipped)
            t["verify_ms"] = int((time.perf_counter() - t2) * 1000)
            manifest["verification"] = rep
            if not rep["checks"].get("xml_roundtrip", False) or not rep["checks"].get("xml_jsonl_parity", False):
                manifest["status"] = "error"
                manifest["exit_code"] = 4
                _emit_manifest(manifest, args.outdir)
                return 4

        _emit_manifest(manifest, args.outdir)
        return 0

    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        _emit_manifest({"status": "error", "exit_code": 1, "category": "internal",
                        "message": f"{type(e).__name__}", "file_name": file_name,
                        "pipeline_version": PIPELINE_VERSION}, args.outdir)
        return 1


if __name__ == "__main__":
    sys.exit(main())
