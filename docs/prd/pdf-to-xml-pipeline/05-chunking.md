# Step 5 · 청킹 전략 (Chunking Strategy) — PDF → RAG Chunk 파이프라인

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §9 · 선행 참조: 00-foundation, 02-structure-recognition
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 9. 청킹 전략 (Chunking Strategy)

- **의미 단위 분할**: 너무 작게 쪼개 문맥 소실 금지, 너무 크게 묶어 검색 품질 저하 금지. 각
  청크는 질문에 답할 만한 의미 완결성을 가진다. 본문은 `max_chunk_chars`(기본 1200) 상한,
  `min_chunk_chars`(기본 80) 하한으로 과분할/과병합을 가드한다.
- **타입별 분할 단위**: 일반 문단=1 청크, 목록 항목=항목당 1 청크, 표=Row당 1 청크, 절차=단계당
  1 청크, 순서도=노드/관계당 1 청크 + graph 1 청크.
- **읽기 순서 고정**: 항상 `(page, y버킷, x버킷)` 정렬로 순회해 seq(형제 순서)를 안정화한다
  (멱등의 전제).
- **content_type 13종**: text, table-row, table-note, list-item, procedure-step, infographic,
  screenshot, flowchart, flowchart-edge, graph, warning, footnote, reference.

---
