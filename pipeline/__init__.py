"""PDF → RAG Chunk 변환 파이프라인.

설계·계약: docs/prd/PRD.md §8 (파이프라인 요구사항 & 핵심 계약)
산출물: chunks.xml(원본 정본) + chunks.jsonl(검색용) + manifest.json
"""

PIPELINE_VERSION = "1.0.0"
