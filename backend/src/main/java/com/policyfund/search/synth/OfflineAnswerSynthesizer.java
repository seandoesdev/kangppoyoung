package com.policyfund.search.synth;

import com.policyfund.search.dto.Article;
import com.policyfund.search.dto.SearchResult;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 오프라인(키 없는) 답변 합성기. LLM 없이 벡터 검색 후보를 결정적으로 그대로 근거로 제시한다.
 * search.synth.provider 가 없거나 "offline" 일 때 활성화(기본값). OpenAI 합성은 "openai" 일 때만.
 *
 * <p>근거 없는 답 금지(PRD 원칙)에 맞춰, 답변은 검색된 상위 후보의 출처를 명시할 뿐 새로운 사실을
 * 생성하지 않는다. 중복/상충 분석은 LLM 영역이므로 오프라인에서는 수행하지 않는다(null).
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "offline", matchIfMissing = true)
public class OfflineAnswerSynthesizer implements AnswerSynthesizer {

    private static final int MAX_EVIDENCE = 5;

    @Override
    public SearchResult synthesize(String query, List<Article> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return new SearchResult(query, "관련 근거 조항을 찾지 못했습니다.", List.of(), null, null);
        }
        List<Article> evidence = candidates.stream().limit(MAX_EVIDENCE).toList();
        Article top = evidence.get(0);
        String answer = "질의와 가장 관련 있는 근거 조항 " + evidence.size()
                + "건을 찾았습니다. 대표 근거: [" + top.docTitle()
                + (top.articleNo() == null || top.articleNo().isBlank() ? "" : " " + top.articleNo())
                + "]. 아래 근거 조항 원문을 확인하세요.";
        return new SearchResult(query, answer, evidence, null, null);
    }
}
