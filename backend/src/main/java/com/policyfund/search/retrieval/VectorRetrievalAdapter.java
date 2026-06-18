package com.policyfund.search.retrieval;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.policyfund.search.dto.Article;
import com.policyfund.search.embedding.ChunkEmbeddingEntity;
import com.policyfund.search.embedding.ChunkEmbeddingRepository;
import com.policyfund.search.embedding.EmbeddingProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Comparator;
import java.util.List;

/**
 * 벡터(코사인 유사도) 기반 검색 어댑터. 질의를 임베딩하고 chunk_embedding 전량을 로드해
 * 코사인 유사도로 정렬, 상위 20개를 Article 로 매핑한다(브루트포스, MySQL 8.0 호환).
 * search.retrieval=vector 일 때 활성화.
 */
@Component
@ConditionalOnProperty(name = "search.retrieval", havingValue = "vector")
public class VectorRetrievalAdapter implements RetrievalPort {

    private static final int TOP_K = 20;

    private final ChunkEmbeddingRepository repository;
    private final EmbeddingProvider embeddingProvider;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public VectorRetrievalAdapter(ChunkEmbeddingRepository repository, EmbeddingProvider embeddingProvider) {
        this.repository = repository;
        this.embeddingProvider = embeddingProvider;
    }

    @Override
    public List<Article> search(String query) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        float[] queryVector = embeddingProvider.embed(query);
        return repository.findAll().stream()
                .map(entity -> new Scored(entity, cosine(queryVector, parse(entity.getEmbeddingJson()))))
                .sorted(Comparator.comparingDouble(Scored::score).reversed())
                .limit(TOP_K)
                .map(scored -> toArticle(scored.entity()))
                .toList();
    }

    private static Article toArticle(ChunkEmbeddingEntity e) {
        return new Article(e.getDocumentId(), e.getFileName(), e.getContentType(),
                e.getArticleNo(), e.getEmbeddingText());
    }

    private float[] parse(String embeddingJson) {
        try {
            return objectMapper.readValue(embeddingJson, float[].class);
        } catch (IOException ex) {
            throw new UncheckedIOException("embedding JSON 파싱 실패", ex);
        }
    }

    /** 코사인 유사도. 길이가 다르거나 영벡터면 0. */
    static double cosine(float[] a, float[] b) {
        if (a == null || b == null || a.length != b.length) {
            return 0.0;
        }
        double dot = 0.0;
        double normA = 0.0;
        double normB = 0.0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            normA += (double) a[i] * a[i];
            normB += (double) b[i] * b[i];
        }
        if (normA == 0.0 || normB == 0.0) {
            return 0.0;
        }
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    private record Scored(ChunkEmbeddingEntity entity, double score) {}
}
