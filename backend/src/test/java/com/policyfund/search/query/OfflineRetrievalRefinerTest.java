package com.policyfund.search.query;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/** 오프라인 점검기는 항상 '충분'을 반환해 2차 검색을 막는다(Docker 불필요). */
class OfflineRetrievalRefinerTest {

    @Test
    void alwaysSufficient() {
        RefineDecision d = new OfflineRetrievalRefiner()
                .evaluate("정책자금 신청 절차", QueryPlan.trivial("정책자금 신청 절차"), List.of());

        assertThat(d.needsMore()).isFalse();
        assertThat(d.followUpQuery()).isBlank();
    }
}
