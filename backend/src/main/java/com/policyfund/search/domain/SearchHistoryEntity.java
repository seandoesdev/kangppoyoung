package com.policyfund.search.domain;

import com.policyfund.search.dto.SearchResult;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

@Entity
@Table(name = "search_history")
public class SearchHistoryEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // URL(/q/<session_id>) 식별용 UUID. 행 생성 시 부여한다.
    @Column(name = "session_id", nullable = false, unique = true, length = 36)
    private String sessionId;

    private String query;

    @Column(columnDefinition = "TEXT")
    private String answer;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "result_json", columnDefinition = "json")
    private SearchResult resultJson;

    @Column(name = "created_at")
    private Instant createdAt;

    protected SearchHistoryEntity() {}

    public SearchHistoryEntity(String sessionId, String query, String answer, SearchResult resultJson, Instant createdAt) {
        this.sessionId = sessionId;
        this.query = query;
        this.answer = answer;
        this.resultJson = resultJson;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getSessionId() { return sessionId; }
    public String getQuery() { return query; }
    public String getAnswer() { return answer; }
    public Instant getCreatedAt() { return createdAt; }
    public SearchResult getResultJson() { return resultJson; }
}
