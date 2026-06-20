package com.policyfund.search.query;

import com.policyfund.search.dto.Article;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 오프라인(키 없는) 모드용 무점검 폴백. search.synth.provider 가 openai 가 아니면 활성화되어
 * 항상 '충분'을 반환한다 → 2차 검색 없이 기존 1-hop 으로 동작.
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "offline", matchIfMissing = true)
public class OfflineRetrievalRefiner implements RetrievalRefiner {

    @Override
    public RefineDecision evaluate(String query, QueryPlan plan, List<Article> candidates) {
        return RefineDecision.sufficient();
    }
}
