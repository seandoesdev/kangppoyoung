package com.policyfund.rankings;

import com.policyfund.rankings.categorize.CategoryGroup;
import com.policyfund.rankings.categorize.QuestionCategorizer;
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

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@AutoConfigureMockMvc
class RankingApiIntegrationTest extends AbstractIntegrationTest {

    @TestConfiguration
    static class Mocks {
        @Bean @Primary
        QuestionCategorizer categorizer() {
            return queries -> queries.isEmpty() ? List.of()
                    : List.of(new CategoryGroup("서류 제출 기한", queries.get(0), List.of()));
        }
        @Bean @Primary
        com.policyfund.search.synth.AnswerSynthesizer synth() {
            return (q, p, c) -> new com.policyfund.search.dto.SearchResult(q, "ans", List.of(), null, null);
        }
    }

    @Autowired MockMvc mvc;

    @Test
    void rankings_requirePeriod_andReturnCategories() throws Exception {
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"서류 제출 기한 알려줘\"}")).andExpect(status().isOk());

        mvc.perform(get("/api/v1/rankings").param("period", "최근 30일"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$").isArray())
           .andExpect(jsonPath("$[0].rank").value(1))
           .andExpect(jsonPath("$[0].category").exists())
           .andExpect(jsonPath("$[0].trend").exists());
    }

    @Test
    void rankings_missingPeriod_returns400() throws Exception {
        mvc.perform(get("/api/v1/rankings"))
           .andExpect(status().isBadRequest());
    }
}
