package com.policyfund.search.query;

import com.policyfund.search.dto.Article;

import java.util.List;

/**
 * 바운드 2-hop 자기교정 검색의 점검 단계. 1차 검색 후보가 질의 의도(특히 절차·목록의 전체 항목)를
 * 충분히 덮는지 판단하고, 부족하면 빠진 부분을 찾을 추가 검색문을 제안한다({@link RefineDecision}).
 */
public interface RetrievalRefiner {
    RefineDecision evaluate(String query, QueryPlan plan, List<Article> candidates);
}
