package com.policyfund.search.query;

import com.policyfund.search.dto.Article;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * LLM 커버리지 점검기. 1차 후보의 '섹션 + 요약' 다이제스트를 보고 의도를 충분히 덮는지 판단한다.
 * 부족하면 빠진 부분을 찾을 추가 검색문(followUpQuery)을 생성해 hop-2 를 유도한다.
 * search.synth.provider=openai 일 때 활성화. 실패 시 '충분'으로 폴백(1-hop 유지).
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "openai")
public class OpenAiRetrievalRefiner implements RetrievalRefiner {

    private static final int DIGEST_LIMIT = 24; // 점검에 보여줄 후보 수(토큰 절약)
    private static final int SNIPPET = 80;       // 후보 요약 길이

    private static final String SYSTEM = """
            너는 검색 결과 점검기다. 사용자 질의·의도와 '현재 후보(섹션 | 요약)'를 보고, 답을 만들기에
            후보가 충분한지 판단하라.
            - answerType 이 절차·목록인데 전체 단계·항목이 후보에 다 들어있지 않으면 needsMore=true.
            - needsMore=true 면 missing 에 빠진 부분을, followUpQuery 에 그 빠진 부분만 겨냥한 검색
              키워드 나열을 채운다(이미 충분한 부분은 반복하지 말 것).
            - 핵심이 이미 있으면 needsMore=false (missing/followUpQuery 는 빈 문자열). 과잉 재검색 금지.
            """;

    private final ChatClient chatClient;

    public OpenAiRetrievalRefiner(ChatClient.Builder builder) {
        this.chatClient = builder.defaultSystem(SYSTEM).build();
    }

    @Override
    public RefineDecision evaluate(String query, QueryPlan plan, List<Article> candidates) {
        try {
            String digest = candidates.stream().limit(DIGEST_LIMIT)
                    .map(a -> "- [" + a.articleNo() + "] " + snippet(a.text()))
                    .reduce("", (x, y) -> x + "\n" + y);
            String user = "질의: " + query
                    + "\n의도: " + plan.intent() + " / 유형: " + plan.answerType()
                    + " / 집중: " + (plan.focus() == null || plan.focus().isBlank() ? "(없음)" : plan.focus())
                    + "\n\n현재 후보:\n" + digest;
            RefineDecision decision = chatClient.prompt().user(user).call().entity(RefineDecision.class);
            return decision != null ? decision : RefineDecision.sufficient();
        } catch (RuntimeException ex) {
            return RefineDecision.sufficient(); // 점검 실패 시 추가 검색 없이 진행.
        }
    }

    private static String snippet(String text) {
        if (text == null) {
            return "";
        }
        String s = text.strip();
        return s.length() <= SNIPPET ? s : s.substring(0, SNIPPET);
    }
}
