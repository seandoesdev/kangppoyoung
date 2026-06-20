package com.policyfund.search.embedding;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * chunk_embedding 행. 임베딩 벡터는 JSON 문자열(float 배열 직렬화)로 저장한다.
 * float[] <-> JSON 변환은 호출부(ChunkIngestService/VectorRetrievalAdapter)에서 Jackson 으로 처리한다.
 */
@Entity
@Table(name = "chunk_embedding")
public class ChunkEmbeddingEntity {

    @Id
    @Column(name = "chunk_id")
    private String chunkId;

    @Column(name = "document_id")
    private String documentId;

    @Column(name = "file_name")
    private String fileName;

    @Column(name = "content_type")
    private String contentType;

    @Column(name = "article_no")
    private String articleNo;

    @Column(name = "embedding_text")
    private String embeddingText;

    @Column(name = "embedding", columnDefinition = "json")
    private String embeddingJson;

    @Column(name = "dim")
    private int dim;

    /** 문서 내 reading-order 순번(0-based). 부모-문서 확장(이웃 청크)을 위한 키. */
    @Column(name = "seq_no")
    private int seqNo;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    protected ChunkEmbeddingEntity() {}

    public ChunkEmbeddingEntity(String chunkId, String documentId, String fileName, String contentType,
                                String articleNo, String embeddingText, String embeddingJson, int dim,
                                int seqNo, LocalDateTime createdAt) {
        this.chunkId = chunkId;
        this.documentId = documentId;
        this.fileName = fileName;
        this.contentType = contentType;
        this.articleNo = articleNo;
        this.embeddingText = embeddingText;
        this.embeddingJson = embeddingJson;
        this.dim = dim;
        this.seqNo = seqNo;
        this.createdAt = createdAt;
    }

    public String getChunkId() { return chunkId; }
    public String getDocumentId() { return documentId; }
    public String getFileName() { return fileName; }
    public String getContentType() { return contentType; }
    public String getArticleNo() { return articleNo; }
    public String getEmbeddingText() { return embeddingText; }
    public String getEmbeddingJson() { return embeddingJson; }
    public int getDim() { return dim; }
    public int getSeqNo() { return seqNo; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
