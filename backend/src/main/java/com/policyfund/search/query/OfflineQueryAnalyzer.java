package com.policyfund.search.query;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 오프라인(키 없는) 모드용 무분석 폴백. search.synth.provider 가 openai 가 아니면 활성화되어
 * 원 질의를 그대로 검색어로 쓰는 trivial QueryPlan 을 반환한다(LLM 분석 없음).
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "offline", matchIfMissing = true)
public class OfflineQueryAnalyzer implements QueryAnalyzer {

    @Override
    public QueryPlan analyze(String query) {
        return QueryPlan.trivial(query);
    }
}
