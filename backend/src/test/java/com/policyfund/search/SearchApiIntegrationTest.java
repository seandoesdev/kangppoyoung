package com.policyfund.search;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.policyfund.search.dto.Article;
import com.policyfund.search.dto.SearchResult;
import com.policyfund.search.synth.AnswerSynthesizer;
import com.policyfund.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@AutoConfigureMockMvc
class SearchApiIntegrationTest extends AbstractIntegrationTest {

    @TestConfiguration
    static class MockSynth {
        @Bean @Primary
        AnswerSynthesizer synth() {
            return (query, plan, candidates) -> new SearchResult(
                    query,
                    "서류 제출 기한은 공고일로부터 30일 이내입니다.",
                    List.of(new Article("D-100", "지원 규정", "규정", "제5조", "제출 기한 30일")),
                    null, null);
        }
    }

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void search_returnsAnswerWithEvidence() throws Exception {
        mvc.perform(post("/api/v1/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"서류 제출 기한\"}"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.query").value("서류 제출 기한"))
           .andExpect(jsonPath("$.answer").exists())
           .andExpect(jsonPath("$.evidence[0].docId").value("D-100"));
    }

    @Test
    void search_blankQuery_returns400() throws Exception {
        mvc.perform(post("/api/v1/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"\"}"))
           .andExpect(status().isBadRequest());
    }

    @Test
    void history_returnsLatestFirst() throws Exception {
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"첫번째 질의\"}")).andExpect(status().isOk());
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"두번째 질의\"}")).andExpect(status().isOk());

        mvc.perform(get("/api/v1/search/history").param("page", "0").param("size", "20"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$").isArray())
           .andExpect(jsonPath("$[0].query").value("두번째 질의"))
           .andExpect(jsonPath("$[0].id").exists())
           .andExpect(jsonPath("$[0].sessionId").exists())
           .andExpect(jsonPath("$[0].createdAt").exists());
    }

    @Test
    void deleteHistory_removesThatRow() throws Exception {
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"삭제대상 질의\"}")).andExpect(status().isOk());

        // 방금 저장된 최신 1건의 sessionId 추출
        String body = mvc.perform(get("/api/v1/search/history").param("page", "0").param("size", "1"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        JsonNode arr = objectMapper.readTree(body);
        String sessionId = arr.get(0).get("sessionId").asText();

        mvc.perform(delete("/api/v1/search/history/" + sessionId))
           .andExpect(status().isNoContent());

        // 그 sessionId 는 더 이상 목록에 없어야 한다
        mvc.perform(get("/api/v1/search/history").param("page", "0").param("size", "100"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$[?(@.sessionId == '" + sessionId + "')]").isEmpty());
    }

    @Test
    void deleteHistory_unknownSession_isIdempotent204() throws Exception {
        // 미존재 sessionId(임의 UUID)도 500 이 아니라 멱등 204 여야 한다.
        mvc.perform(delete("/api/v1/search/history/" + java.util.UUID.randomUUID()))
           .andExpect(status().isNoContent());
    }

    @Test
    void getHistoryItem_bySessionId_returnsItem() throws Exception {
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"단건 조회 질의\"}")).andExpect(status().isOk());
        String body = mvc.perform(get("/api/v1/search/history").param("page", "0").param("size", "1"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String sessionId = objectMapper.readTree(body).get(0).get("sessionId").asText();

        mvc.perform(get("/api/v1/search/history/" + sessionId))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.sessionId").value(sessionId))
           .andExpect(jsonPath("$.query").value("단건 조회 질의"))
           .andExpect(jsonPath("$.result").exists());
    }

    @Test
    void getHistoryItem_unknownSession_returns404() throws Exception {
        mvc.perform(get("/api/v1/search/history/" + java.util.UUID.randomUUID()))
           .andExpect(status().isNotFound());
    }

    @Test
    void clearHistory_removesAll() throws Exception {
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"지우기 대상 1\"}")).andExpect(status().isOk());
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"지우기 대상 2\"}")).andExpect(status().isOk());

        mvc.perform(delete("/api/v1/search/history"))
           .andExpect(status().isNoContent());

        mvc.perform(get("/api/v1/search/history").param("page", "0").param("size", "100"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.length()").value(0));
    }
}
