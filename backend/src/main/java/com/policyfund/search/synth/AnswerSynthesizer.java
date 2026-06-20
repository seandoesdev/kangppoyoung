package com.policyfund.search.synth;

import com.policyfund.search.dto.Article;
import com.policyfund.search.dto.SearchResult;
import com.policyfund.search.query.QueryPlan;

import java.util.List;

/**
 * 질의 + 질의 분석(QueryPlan) + 후보 조항 → 답변(출처 명시, 중복 요약/상충 병렬).
 * QueryPlan 의 intent/answerType/focus 가 답 형태와 집중 범위를 안내한다. OpenAI 호출을 격리한다.
 */
public interface AnswerSynthesizer {
    SearchResult synthesize(String query, QueryPlan plan, List<Article> candidates);
}
