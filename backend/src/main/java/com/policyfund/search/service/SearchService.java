package com.policyfund.search.service;

import com.policyfund.search.domain.SearchHistoryEntity;
import com.policyfund.search.domain.SearchHistoryRepository;
import com.policyfund.search.dto.Article;
import com.policyfund.search.dto.SearchHistoryItem;
import com.policyfund.search.dto.SearchResult;
import com.policyfund.search.query.QueryAnalyzer;
import com.policyfund.search.query.QueryPlan;
import com.policyfund.search.query.RefineDecision;
import com.policyfund.search.query.RetrievalRefiner;
import com.policyfund.search.retrieval.CandidateMerge;
import com.policyfund.search.retrieval.RetrievalPort;
import com.policyfund.search.synth.AnswerSynthesizer;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
public class SearchService {

    // 2-hop 병합 시 섹션당/전체 후보 한도(과대표집 섹션의 재범람 차단).
    private static final int MERGE_MAX_PER_SECTION = 18;
    private static final int MERGE_MAX_CANDIDATES = 90;
    // 분석기 확장 질의 : 원 질의 보강 가중비(2:1). 분석기 질의를 우대하되 원 질의로 간헐 누락 보완.
    private static final int RAW_MERGE_RATIO = 2;

    private final QueryAnalyzer queryAnalyzer;
    private final RetrievalRefiner refiner;
    private final RetrievalPort retrieval;
    private final AnswerSynthesizer synthesizer;
    private final SearchHistoryRepository history;

    public SearchService(QueryAnalyzer queryAnalyzer, RetrievalRefiner refiner, RetrievalPort retrieval,
                         AnswerSynthesizer synthesizer, SearchHistoryRepository history) {
        this.queryAnalyzer = queryAnalyzer;
        this.refiner = refiner;
        this.retrieval = retrieval;
        this.synthesizer = synthesizer;
        this.history = history;
    }

    @Transactional
    public SearchResult search(String query) {
        // 바운드 2-hop: 1) 의도 분석 → 2) 1차 검색 → (절차/목록이면 커버리지 점검 후 부족하면 1회 타깃 재검색)
        //              → 3) 분석+원 질의로 답변 합성.
        QueryPlan plan = queryAnalyzer.analyze(query);
        // 안정 회수: 원 질의(결정적 임베딩)와 분석기 확장 질의를 각각 검색해 교차 병합한다.
        // 분석기 searchTerms 가 실행마다 달라져 핵심 청크가 빠지던 문제(Q4·Q8 간헐 누락)를, 양쪽 검색의
        // 상위를 모두 후보에 담아 완화한다.
        String expanded = plan.retrievalQuery(query);
        List<Article> candidates = retrieval.search(expanded);
        if (!expanded.equals(query)) {
            // 분석기 확장 질의를 2:1 로 우대(보통 더 정밀)하고, 원 질의 결과를 보강 주입한다.
            candidates = CandidateMerge.interleave(candidates, retrieval.search(query),
                    RAW_MERGE_RATIO, MERGE_MAX_PER_SECTION, MERGE_MAX_CANDIDATES);
        }
        if (isProcedureLike(plan)) {
            RefineDecision decision = refiner.evaluate(query, plan, candidates);
            if (decision.needsMore()
                    && decision.followUpQuery() != null && !decision.followUpQuery().isBlank()) {
                List<Article> more = retrieval.search(decision.followUpQuery());
                candidates = CandidateMerge.mergeAndCap(candidates, more,
                        MERGE_MAX_PER_SECTION, MERGE_MAX_CANDIDATES);
            }
        }
        SearchResult result = synthesizer.synthesize(query, plan, candidates);
        history.save(new SearchHistoryEntity(
                UUID.randomUUID().toString(), query, result.answer(), result, Instant.now()));
        return result;
    }

    /** 전체 항목 회수가 중요한 절차·목록·순서 질의에만 hop-2 점검을 가동(비용 절감 게이트). */
    private static boolean isProcedureLike(QueryPlan plan) {
        String type = plan.answerType();
        return type != null && (type.contains("절차") || type.contains("목록") || type.contains("순서"));
    }

    @Transactional(readOnly = true)
    public List<SearchHistoryItem> history(int page, int size) {
        return history.findAllByOrderByCreatedAtDesc(PageRequest.of(page, size)).stream()
                .map(SearchService::toItem)
                .toList();
    }

    /** 세션 id(UUID)로 단건 조회. */
    @Transactional(readOnly = true)
    public Optional<SearchHistoryItem> bySession(String sessionId) {
        return history.findBySessionId(sessionId).map(SearchService::toItem);
    }

    /** 세션 id(UUID) 1건 삭제. 미존재 sessionId 는 조용히 무시(멱등 204). */
    @Transactional
    public void deleteHistory(String sessionId) {
        history.findBySessionId(sessionId).ifPresent(history::delete);
    }

    /** 검색 기록 전체 삭제(단일 DELETE). */
    @Transactional
    public void clearHistory() {
        history.deleteAllInBatch();
    }

    private static SearchHistoryItem toItem(SearchHistoryEntity h) {
        return new SearchHistoryItem(
                String.valueOf(h.getId()), h.getSessionId(), h.getQuery(), h.getCreatedAt(), h.getResultJson());
    }
}
