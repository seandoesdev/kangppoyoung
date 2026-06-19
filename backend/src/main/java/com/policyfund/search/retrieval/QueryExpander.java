package com.policyfund.search.retrieval;

/**
 * 사용자 자연어 질의를 벡터 검색 회수율이 높은 '확장 검색문'으로 변환한다.
 * 청크가 잘게 쪼개져 있어(예: 절차의 각 단계가 별도 청크) 전체 절차·목록을 묻는 자연어 질의는
 * 개별 단계 청크와 임베딩 매칭이 약하다. 확장으로 관련 용어를 보강해 회수율을 높인다.
 */
public interface QueryExpander {
    String expand(String query);
}
