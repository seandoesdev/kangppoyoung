CREATE TABLE policy_document (
    id               VARCHAR(64)  NOT NULL PRIMARY KEY,
    title            VARCHAR(500) NOT NULL,
    type             VARCHAR(10)  NOT NULL,
    updated_at       DATE         NOT NULL,
    is_single_source BOOLEAN      NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE article (
    id         BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    doc_id     VARCHAR(64)  NOT NULL,
    doc_title  VARCHAR(500) NOT NULL,
    doc_type   VARCHAR(10)  NOT NULL,
    article_no VARCHAR(100) NOT NULL,
    `text`     TEXT         NOT NULL,
    CONSTRAINT fk_article_doc FOREIGN KEY (doc_id) REFERENCES policy_document(id),
    FULLTEXT INDEX ft_article_text (`text`) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE search_history (
    id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    query       VARCHAR(500) NOT NULL,
    answer      TEXT         NULL,
    result_json JSON         NULL,
    created_at  DATETIME(6)  NOT NULL,
    INDEX idx_search_history_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- search_example: 슬롯(0~4) 유니크로 최대 5개 동시성 안전 보장 (BACKEND_PRD 발견 #4)
CREATE TABLE search_example (
    id         BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    slot       TINYINT      NOT NULL,
    `text`     VARCHAR(500) NOT NULL,
    created_at DATETIME(6)  NOT NULL,
    CONSTRAINT uq_search_example_slot UNIQUE (slot),
    CONSTRAINT ck_search_example_slot CHECK (slot BETWEEN 0 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE notice_category (
    `key`     VARCHAR(20)  NOT NULL PRIMARY KEY,
    label     VARCHAR(100) NOT NULL,
    doc_title VARCHAR(500) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE notice_version (
    id           BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category_key VARCHAR(20) NOT NULL,
    version      VARCHAR(20) NOT NULL,
    `date`       DATE        NOT NULL,
    blocks_json  JSON        NOT NULL,
    CONSTRAINT fk_version_category FOREIGN KEY (category_key) REFERENCES notice_category(`key`),
    CONSTRAINT uq_version UNIQUE (category_key, version),
    INDEX idx_version_date (category_key, `date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ranking_cache (
    id                    BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    period                VARCHAR(20)  NOT NULL,
    category              VARCHAR(255) NOT NULL,
    question_example      VARCHAR(500) NULL,
    search_count          INT          NOT NULL DEFAULT 0,
    view_count            INT          NOT NULL DEFAULT 0,
    trend                 VARCHAR(10)  NOT NULL,
    related_articles_json JSON         NULL,
    computed_at           DATETIME(6)  NOT NULL,
    INDEX idx_ranking_period (period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
