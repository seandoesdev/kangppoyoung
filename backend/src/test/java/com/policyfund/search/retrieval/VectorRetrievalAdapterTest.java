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

/**
 * 벡터 검색 어댑터 검증(Docker 불필요): 코사인 랭킹·Article 필드 매핑,
 * 부모-문서(small-to-big) 이웃 확장, 후보 상한.
 */
class VectorRetrievalAdapterTest {

    private static final int MAX_CANDIDATES = 90;

    private final HashingEmbeddingProvider embeddingProvider = new HashingEmbeddingProvider();
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final ChunkEmbeddingRepository repository = mock(ChunkEmbeddingRepository.class);
    private final VectorRetrievalAdapter adapter = new VectorRetrievalAdapter(repository, embeddingProvider);

    private ChunkEmbeddingEntity entity(String chunkId, String docId, int seqNo, String fileName,
                                        String contentType, String articleNo, String embeddingText) {
        float[] vec = embeddingProvider.embed(embeddingText);
        String json;
        try {
            json = objectMapper.writeValueAsString(vec);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        return new ChunkEmbeddingEntity(chunkId, docId, fileName, contentType, articleNo,
                embeddingText, json, vec.length, seqNo, LocalDateTime.now());
    }

    @Test
    void rankingMatchingChunkFirstAndMapsFields() {
        ChunkEmbeddingEntity match = entity("c1", "d1", 0, "융자공고.pdf", "text", "제3조",
                "정책자금 융자 신청 서류 제출 기한과 절차 안내");
        ChunkEmbeddingEntity unrelated = entity("c2", "d2", 0, "가이드.pdf", "text", "p.5",
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
    void expandsHitToReadingOrderNeighbors() {
        String query = "정책자금 융자 신청 서류 제출 기한 안내";
        // 절차 문서 dA: seq2 만 질의와 정확히 일치(최상위 히트), 나머지 단계는 질의 토큰을 공유하지 않음.
        List<ChunkEmbeddingEntity> rows = new ArrayList<>();
        rows.add(entity("a0", "dA", 0, "공고.pdf", "text", "절차", "사무 비품 청소 일정 영단계"));
        rows.add(entity("a1", "dA", 1, "공고.pdf", "text", "절차", "사무 비품 청소 일정 일단계"));
        rows.add(entity("a2", "dA", 2, "공고.pdf", "text", "절차", query));
        rows.add(entity("a3", "dA", 3, "공고.pdf", "text", "절차", "사무 비품 청소 일정 삼단계"));
        rows.add(entity("a4", "dA", 4, "공고.pdf", "text", "절차", "사무 비품 청소 일정 사단계"));
        // 질의 토큰을 일부 공유해 이웃(코사인 0)보다 확실히 높게 랭크되는 필러 50개(서로 다른 문서, 이웃 없음).
        for (int i = 0; i < 50; i++) {
            rows.add(entity("f" + i, "f" + i, 0, "f.pdf", "text", "p.1", "정책자금 융자 신청 서류"));
        }
        when(repository.findAll()).thenReturn(rows);

        List<Article> results = adapter.search(query);
        List<String> texts = results.stream().map(Article::text).toList();

        // 최상위 히트(a2)의 reading-order 이웃들이, 자체로는 상위 히트가 아니어도 함께 끌려와야 한다.
        assertThat(texts).contains(query,
                "사무 비품 청소 일정 영단계", "사무 비품 청소 일정 일단계",
                "사무 비품 청소 일정 삼단계", "사무 비품 청소 일정 사단계");
    }

    @Test
    void diversityCap_letsUnderRepresentedSectionIn() {
        // 한 섹션(dA|A절차)이 50개로 과대표집, 다른 섹션(dB|B절차)은 1개. 둘 다 질의와 동일(코사인 1.0).
        // 섹션 캡이 없으면 dA 가 top-K(40)를 독점해 dB 가 후보에서 빠지고, dB 는 다른 문서라 이웃 확장도 못 미친다.
        String query = "정책자금 융자 신청 서류 제출 기한";
        List<ChunkEmbeddingEntity> rows = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
            rows.add(entity("a" + i, "dA", i, "a.pdf", "text", "A절차", query));
        }
        rows.add(entity("bOnly", "dB", 0, "b.pdf", "text", "B절차", query));
        when(repository.findAll()).thenReturn(rows);

        List<Article> results = adapter.search(query);

        // 섹션 다양화 덕분에 과소표집 섹션(dB)의 청크가 후보에 포함된다.
        assertThat(results).anyMatch(a -> "dB".equals(a.docId()));
    }

    @Test
    void documentQuota_includesRelevantOtherDocument_andGatesIrrelevant() {
        String query = "정책자금 융자 신청 서류 제출 기한";
        List<ChunkEmbeddingEntity> rows = new ArrayList<>();
        // 우세 문서 dMain: 8섹션 × 6청크 = 48, 모두 질의와 동일(코사인 1.0). 단독으로 top-K를 채울 수 있음.
        for (int i = 0; i < 48; i++) {
            rows.add(entity("m" + i, "dMain", i, "main.pdf", "text", "S" + (i / 6), query));
        }
        // 관련 있는 다른 문서 dAlt(질의 동일, 1청크) — 문서 쿼터가 없으면 dMain 물량에 밀려 후보에서 빠짐.
        rows.add(entity("alt", "dAlt", 0, "alt.pdf", "text", "A", query));
        // 무관한 문서 dNoise(질의 토큰 0) — 관련도 게이트에서 제외되어야 함.
        rows.add(entity("noise", "dNoise", 0, "noise.pdf", "text", "N", "사무 비품 청소 일정 공지"));
        when(repository.findAll()).thenReturn(rows);

        List<Article> results = adapter.search(query);

        assertThat(results).anyMatch(a -> "dAlt".equals(a.docId()));    // 문서 쿼터로 포함
        assertThat(results).noneMatch(a -> "dNoise".equals(a.docId())); // 관련도 게이트로 제외
    }

    @Test
    void capsCandidatesAtMax() {
        // 한 문서에 연속 seq 청크를 충분히 많이 두어, 히트 + 이웃 확장이 상한을 넘게 만든다.
        List<ChunkEmbeddingEntity> rows = new ArrayList<>();
        for (int i = 0; i < 400; i++) {
            rows.add(entity("c" + i, "dBig", i, "f.pdf", "text", "p.1",
                    "정책자금 융자 신청 서류 제출 기한 안내 " + i));
        }
        when(repository.findAll()).thenReturn(rows);

        List<Article> results = adapter.search("정책자금 융자 신청 서류");

        assertThat(results).hasSizeLessThanOrEqualTo(MAX_CANDIDATES);
    }

    @Test
    void blankQueryReturnsEmpty() {
        assertThat(adapter.search("  ")).isEmpty();
    }
}
