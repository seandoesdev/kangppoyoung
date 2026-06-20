package com.policyfund.search.query;

/**
 * 1차 검색 후보의 커버리지 점검 결과. needsMore=true 면 followUpQuery 로 2차 검색(hop-2)을 수행한다.
 *
 * @param needsMore     후보가 의도를 충분히 덮지 못해 추가 검색이 필요한가
 * @param missing       빠진 부분(설명, 없으면 빈 문자열)
 * @param followUpQuery 빠진 부분을 찾을 추가 검색문(키워드 나열, 없으면 빈 문자열)
 */
public record RefineDecision(boolean needsMore, String missing, String followUpQuery) {

    /** 충분함(추가 검색 불필요). */
    public static RefineDecision sufficient() {
        return new RefineDecision(false, "", "");
    }
}
