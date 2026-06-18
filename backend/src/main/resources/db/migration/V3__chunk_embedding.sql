-- 벡터 검색용 청크 임베딩 저장소. MySQL 8.0 호환(JSON 컬럼; VECTOR 미사용, 앱에서 브루트포스 코사인).
-- 적재 원천: pipeline 의 chunks.jsonl (chunk_id/document_id/content_type/embedding_text/metadata).
CREATE TABLE chunk_embedding (
    chunk_id       VARCHAR(80)  NOT NULL PRIMARY KEY,
    document_id    VARCHAR(80)  NOT NULL,  -- "d_" + sha256(64hex) = 66자
    file_name      VARCHAR(500) NULL,
    content_type   VARCHAR(40)  NULL,
    article_no     VARCHAR(512) NULL,  -- heading_path 결합값(긴 한글 경로 대비)
    embedding_text MEDIUMTEXT   NOT NULL,
    embedding      JSON         NOT NULL,
    dim            INT          NOT NULL,
    created_at     DATETIME(6)  NOT NULL,
    INDEX idx_chunk_doc (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
