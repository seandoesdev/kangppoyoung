package com.policyfund.search.retrieval;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * LLM 기반 질의 확장기. 전체 절차·목록을 묻는 자연어 질의(예: "신청부터 사후관리까지 어떤 순서로")는
 * 단계별로 쪼개진 청크와 임베딩 매칭이 약하므로, 질의의 핵심 개념·동의어와 (절차/목록 질의인 경우)
 * 그 단계·항목 용어를 함께 나열해 검색 회수율을 끌어올린다. search.synth.provider=openai 일 때 활성화.
 */
@Component
@ConditionalOnProperty(name = "search.synth.provider", havingValue = "openai")
public class OpenAiQueryExpander implements QueryExpander {

    private static final String SYSTEM = """
            너는 검색 질의 확장기다. 사용자 질의를 정책자금 규정·공고 문서의 벡터 검색에 쓸 한 줄짜리
            '확장 검색문'으로 바꿔라. 규칙:
            - 질의의 핵심 개념과 동의어를 포함한다.
            - 질의가 절차·순서·단계·목록을 물으면, 그 절차에 포함될 법한 단계·항목 용어를 빠짐없이 나열한다.
            - 설명·완성된 문장 없이, 공백으로 구분된 키워드/구 나열만 한 줄로 출력한다.
            """;

    private final ChatClient chatClient;

    public OpenAiQueryExpander(ChatClient.Builder builder) {
        this.chatClient = builder.defaultSystem(SYSTEM).build();
    }

    @Override
    public String expand(String query) {
        try {
            String expanded = chatClient.prompt().user(query).call().content();
            if (expanded == null || expanded.isBlank()) {
                return query;
            }
            // 원 질의 + 확장어를 함께 임베딩해 정밀도와 회수율을 모두 확보한다.
            return query + " " + expanded.trim();
        } catch (RuntimeException ex) {
            return query; // 확장 실패 시 원 질의로 폴백(검색은 계속 동작).
        }
    }
}
