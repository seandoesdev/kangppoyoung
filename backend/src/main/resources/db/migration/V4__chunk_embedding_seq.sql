-- 부모-문서(small-to-big) 검색용: 문서 내 reading-order 순번(seq_no).
-- pipeline 의 chunks.jsonl 은 reading order 로 기록되므로, 적재 시 문서별 0-based 순번을 부여한다.
-- 검색 히트의 이웃 청크(같은 섹션의 연속 청크)를 seq_no 창으로 확장해 LLM 에 통째로 전달한다.
ALTER TABLE chunk_embedding ADD COLUMN seq_no INT NOT NULL DEFAULT 0;
CREATE INDEX idx_chunk_doc_seq ON chunk_embedding (document_id, seq_no);
