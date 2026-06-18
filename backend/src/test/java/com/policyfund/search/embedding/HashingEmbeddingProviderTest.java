package com.policyfund.search.embedding;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

/** 오프라인 해싱 임베딩의 결정성·차원·정규화·의미적 근접성 검증(Docker 불필요). */
class HashingEmbeddingProviderTest {

    private final HashingEmbeddingProvider provider = new HashingEmbeddingProvider();

    @Test
    void sameTextProducesIdenticalVector() {
        String text = "중소기업 정책자금 융자 신청 서류 제출 기한";
        assertThat(provider.embed(text)).containsExactly(provider.embed(text));
    }

    @Test
    void dimensionsIs256() {
        assertThat(provider.dimensions()).isEqualTo(256);
        assertThat(provider.embed("아무 텍스트")).hasSize(256);
    }

    @Test
    void nonEmptyVectorIsL2Normalized() {
        float[] vec = provider.embed("정책자금 신청 절차 안내");
        double norm = 0.0;
        for (float v : vec) {
            norm += (double) v * v;
        }
        assertThat(Math.sqrt(norm)).isCloseTo(1.0, within(1e-6));
    }

    @Test
    void blankTextYieldsZeroVector() {
        float[] vec = provider.embed("   ");
        for (float v : vec) {
            assertThat(v).isEqualTo(0.0f);
        }
    }

    @Test
    void nearIdenticalTextsAreCloserThanUnrelated() {
        float[] base = provider.embed("정책자금 융자 신청 서류 제출 기한은 언제인가");
        float[] similar = provider.embed("정책자금 융자 신청 서류 제출 기한 문의");
        float[] unrelated = provider.embed("오늘 날씨가 맑고 기온이 높습니다");

        double simSimilar = cosine(base, similar);
        double simUnrelated = cosine(base, unrelated);
        assertThat(simSimilar).isGreaterThan(simUnrelated);
    }

    private static double cosine(float[] a, float[] b) {
        double dot = 0.0;
        double na = 0.0;
        double nb = 0.0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            na += (double) a[i] * a[i];
            nb += (double) b[i] * b[i];
        }
        if (na == 0.0 || nb == 0.0) {
            return 0.0;
        }
        return dot / (Math.sqrt(na) * Math.sqrt(nb));
    }
}
