package com.policyfund.search.query;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * LLM 질의 분석기. 질의를 {@link QueryPlan}(intent/answerType/searchTerms/focus)으로 구조화한다.
 * focus 는 "이 질의가 가리키는 대상/범위와, 비슷하지만 다른 대상과의 구분"을 질의별로 LLM 이 생성하므로
 * 특정 절차쌍을 프롬프트에 하드코딩하지 않아도 된다(일반화). search.synth.provider=openai 일 때 활성화.
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "openai")
public class OpenAiQueryAnalyzer implements QueryAnalyzer {

    private static final String SYSTEM = """
            너는 정책자금 규정·공고 검색의 '질의 분석기'다. 사용자 질의를 분석해 무엇을 찾는지 구조화하라.
            - intent: 사용자가 실제로 알고 싶은 핵심을 한 문장으로.
            - answerType: 절차 | 목록 | 정의 | 자격 | 수치 | 예아니오 | 일반 중 가장 맞는 하나.
            - searchTerms: 벡터 검색에 쓸 핵심 키워드·동의어·관련 용어. 질의가 절차/목록을 물으면
              그 절차·목록에 포함될 법한 단계·항목 용어까지 빠짐없이 넣는다.
            - focus: 답이 집중해야 할 범위. 이름이 비슷하지만 범위·대상이 다른 항목이 있으면 무엇과
              혼동하지 말지 명시한다(예: 하위 세부 절차 vs 전체 절차). 해당 없으면 빈 문자열.
            정책자금 융자 도메인 기준으로, 한국어로 분석하라.
            """;

    private final ChatClient chatClient;

    public OpenAiQueryAnalyzer(ChatClient.Builder builder) {
        this.chatClient = builder.defaultSystem(SYSTEM).build();
    }

    @Override
    public QueryPlan analyze(String query) {
        try {
            QueryPlan plan = chatClient.prompt().user(query).call().entity(QueryPlan.class);
            if (plan == null || plan.searchTerms() == null || plan.searchTerms().isEmpty()) {
                return QueryPlan.trivial(query);
            }
            return plan;
        } catch (RuntimeException ex) {
            return QueryPlan.trivial(query); // 분석 실패 시 원 질의로 폴백(검색은 계속 동작).
        }
    }
}
