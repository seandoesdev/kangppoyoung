package com.policyfund.rankings.service;

import com.policyfund.rankings.dto.OnboardingItem;
import com.policyfund.rankings.dto.RankingItem;
import com.policyfund.search.domain.SearchHistoryEntity;
import com.policyfund.search.domain.SearchHistoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.function.Predicate;

/** UC-5: UC-4 랭킹을 그대로 학습 우선순위로 환산한다(별도 추천 로직 없음). */
@Service
public class OnboardingService {

    private final RankingService rankingService;
    private final SearchHistoryRepository history;

    public OnboardingService(RankingService rankingService, SearchHistoryRepository history) {
        this.rankingService = rankingService;
        this.history = history;
    }

    @Transactional
    public List<OnboardingItem> onboarding(String period) {
        List<RankingItem> rankings = rankingService.rankings(period);
        List<SearchHistoryEntity> rows = history.findAll();
        List<OnboardingItem> items = new ArrayList<>();
        int order = 1;
        for (RankingItem r : rankings) {
            String reason = "실무자 검색 " + r.searchCount() + "회·조회 " + r.viewCount()
                    + "회로 우선순위가 높습니다.";
            String answer = answerFor(rows, r.questionExample());
            items.add(new OnboardingItem(order++, r.category(), r.questionExample(), answer,
                    reason, r.searchCount(), r.viewCount()));
        }
        return items;
    }

    /**
     * 대표 질문에 대해 축적된 답변을 search_history 에서 찾는다(임의 생성이 아닌 실제 데이터 기반).
     * 정확히 일치하는 질의를 우선하고, 없으면 부분 일치(양방향)로 폴백하며, 가장 최근 답변을 쓴다.
     * 매칭되는 기록이 없으면 빈 문자열을 반환한다.
     */
    private static String answerFor(List<SearchHistoryEntity> rows, String questionExample) {
        if (questionExample == null || questionExample.isBlank()) {
            return "";
        }
        Optional<SearchHistoryEntity> hit = latest(rows, q -> q.equals(questionExample));
        if (hit.isEmpty()) {
            hit = latest(rows, q -> q.contains(questionExample) || questionExample.contains(q));
        }
        return hit.map(SearchHistoryEntity::getAnswer).orElse("");
    }

    private static Optional<SearchHistoryEntity> latest(List<SearchHistoryEntity> rows, Predicate<String> match) {
        return rows.stream()
                .filter(h -> h.getQuery() != null && match.test(h.getQuery()))
                .max(Comparator.comparing(h -> h.getCreatedAt() == null ? Instant.EPOCH : h.getCreatedAt()));
    }
}
