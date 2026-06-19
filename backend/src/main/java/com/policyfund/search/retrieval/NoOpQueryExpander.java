package com.policyfund.search.retrieval;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 오프라인(키 없는) 모드용 무확장 폴백. search.synth.provider 가 openai 가 아니면 활성화되어
 * 질의를 그대로 반환한다(LLM 확장 없음).
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "offline", matchIfMissing = true)
public class NoOpQueryExpander implements QueryExpander {

    @Override
    public String expand(String query) {
        return query;
    }
}
