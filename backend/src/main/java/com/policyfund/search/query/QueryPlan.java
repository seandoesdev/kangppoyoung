package com.policyfund.search.query;

import java.util.List;

/**
 * 질의 분석 결과(구조화된 검색 의도). 하드코딩된 도메인 예시 대신, 질의별로 LLM 이 생성한다.
 *
 * @param intent      사용자가 실제로 알고 싶은 것(한 문장)
 * @param answerType  답 형태: 절차 | 목록 | 정의 | 자격 | 수치 | 예아니오 | 일반
 * @param searchTerms 벡터 검색에 쓸 핵심 키워드·동의어·관련 용어
 * @param focus       답이 집중할 범위/혼동 주의점(없으면 빈 문자열)
 */
public record QueryPlan(String intent, String answerType, List<String> searchTerms, String focus) {

    /** 분석 실패·오프라인 폴백: 원 질의를 그대로 검색어로, 유형은 일반. */
    public static QueryPlan trivial(String query) {
        return new QueryPlan(query, "일반", List.of(query), "");
    }

    /** 검색에 쓸 확장 질의(원 질의 + 검색어). */
    public String retrievalQuery(String query) {
        if (searchTerms == null || searchTerms.isEmpty()) {
            return query;
        }
        return query + " " + String.join(" ", searchTerms);
    }
}
