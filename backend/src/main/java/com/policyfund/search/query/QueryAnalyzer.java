package com.policyfund.search.query;

/**
 * 1단계: 사용자 자연어 질의를 분석해 '무엇을 찾는지'를 구조화한다({@link QueryPlan}).
 * 이 구조화 의도가 (2단계) 검색과 (3단계) 답변 합성을 모두 안내하므로, 절차/대상 혼동을
 * 막기 위한 도메인 예시를 프롬프트에 하드코딩할 필요가 없다(질의별로 LLM 이 focus 를 생성).
 */
public interface QueryAnalyzer {
    QueryPlan analyze(String query);
}
