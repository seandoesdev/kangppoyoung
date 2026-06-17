"""PDF → RAG Chunk 변환 파이프라인.

설계: docs/prd/pdf-to-xml-pipeline.md (얼개) + docs/prd/pdf-to-xml-pipeline/*.md
산출물: chunks.xml(원본 정본) + chunks.jsonl(검색용) + manifest.json
"""

PIPELINE_VERSION = "1.0.0"
