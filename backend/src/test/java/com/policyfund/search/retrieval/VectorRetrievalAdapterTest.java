package com.policyfund.search.retrieval;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.policyfund.search.dto.Article;
import com.policyfund.search.embedding.ChunkEmbeddingEntity;
import com.policyfund.search.embedding.ChunkEmbeddingRepository;
import com.policyfund.search.embedding.HashingEmbeddingProvider;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** 벡터 검색 어댑터: 코사인 랭킹·상위 20개 제한·Article 필드 매핑 검증(Docker 불필요). */
class VectorRetrievalAdapterTest {

    private final HashingEmbeddingProvider embeddingProvider = new HashingEmbeddingProvider();
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final ChunkEmbeddingRepository repository = mock(ChunkEmbeddingRepository.class);
    private final VectorRetrievalAdapter adapter = new VectorRetrievalAdapter(repository, embeddingProvider);

    private ChunkEmbeddingEntity entity(String chunkId, String docId, String fileName,
                                        String contentType, String articleNo, String embeddingText) {
        float[] vec = embeddingProvider.embed(embeddingText);
        String json;
        try {
            json = objectMapper.writeValueAsString(vec);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        return new ChunkEmbeddingEntity(chunkId, docId, fileName, contentType, articleNo,
                embeddingText, json, vec.length, LocalDateTime.now());
    }

    @Test
    void rankingMatchingChunkFirstAndMapsFields() {
        ChunkEmbeddingEntity match = entity("c1", "d1", "융자공고.pdf", "text", "제3조",
                "정책자금 융자 신청 서류 제출 기한과 절차 안내");
        ChunkEmbeddingEntity unrelated = entity("c2", "d2", "가이드.pdf", "text", "p.5",
                "사무실 비품 구매 및 청소 일정 공지");
        when(repository.findAll()).thenReturn(List.of(unrelated, match));

        List<Article> results = adapter.search("정책자금 융자 신청 서류 제출 기한");

        assertThat(results).isNotEmpty();
        Article top = results.get(0);
        assertThat(top.docId()).isEqualTo("d1");
        assertThat(top.docTitle()).isEqualTo("융자공고.pdf");
        assertThat(top.docType()).isEqualTo("text");
        assertThat(top.articleNo()).isEqualTo("제3조");
        assertThat(top.text()).isEqualTo("정책자금 융자 신청 서류 제출 기한과 절차 안내");
    }

    @Test
    void capsResultsAt20() {
        List<ChunkEmbeddingEntity> rows = new ArrayList<>();
        for (int i = 0; i < 30; i++) {
            rows.add(entity("c" + i, "d" + i, "f" + i + ".pdf", "text", "p." + i,
                    "정책자금 융자 신청 서류 제출 기한 안내 " + i));
        }
        when(repository.findAll()).thenReturn(rows);

        List<Article> results = adapter.search("정책자금 융자 신청 서류");

        assertThat(results).hasSize(20);
    }

    @Test
    void blankQueryReturnsEmpty() {
        assertThat(adapter.search("  ")).isEmpty();
    }
}
