package com.policyfund.search.synth;

import com.policyfund.search.dto.Article;
import com.policyfund.search.dto.SearchResult;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.assertThat;

class OfflineAnswerSynthesizerTest {

    private final OfflineAnswerSynthesizer synth = new OfflineAnswerSynthesizer();

    @Test
    void emptyCandidates_returnsNoEvidenceAnswer() {
        SearchResult r = synth.synthesize("정책자금 신청 자격", List.of());
        assertThat(r.evidence()).isEmpty();
        assertThat(r.answer()).contains("찾지 못했");
        assertThat(r.query()).isEqualTo("정책자금 신청 자격");
        assertThat(r.duplicateSummary()).isNull();
        assertThat(r.conflicts()).isNull();
    }

    @Test
    void manyCandidates_capsEvidenceAtFiveAndCitesTop() {
        List<Article> candidates = IntStream.range(0, 9)
                .mapToObj(i -> new Article("d_" + i, "기초가이드", "절차", "제" + i + "조", "본문 " + i))
                .toList();

        SearchResult r = synth.synthesize("신청 절차", candidates);

        assertThat(r.evidence()).hasSize(5);
        assertThat(r.evidence().get(0).docId()).isEqualTo("d_0");   // 순서 보존(상위가 먼저)
        assertThat(r.answer()).contains("기초가이드");                 // 대표 근거 출처 명시
    }
}
