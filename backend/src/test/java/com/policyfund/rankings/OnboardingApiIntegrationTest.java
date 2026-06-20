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
class OnboardingApiIntegrationTest extends AbstractIntegrationTest {

    @TestConfiguration
    static class Mocks {
        @Bean @Primary
        QuestionCategorizer categorizer() {
            return queries -> queries.isEmpty() ? List.of()
                    : List.of(new CategoryGroup("온보딩 카테고리", queries.get(0), List.of()));
        }
        @Bean @Primary
        com.policyfund.search.synth.AnswerSynthesizer synth() {
            return (q, p, c) -> new com.policyfund.search.dto.SearchResult(q, "ans", List.of(), null, null);
        }
    }

    @Autowired MockMvc mvc;

    @Test
    void onboarding_defaultsPeriod_andReturnsOrderedItems() throws Exception {
        mvc.perform(post("/api/v1/search").contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"온보딩 학습 항목 질의\"}")).andExpect(status().isOk());

        mvc.perform(get("/api/v1/onboarding"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$").isArray())
           .andExpect(jsonPath("$[0].order").value(1))
           .andExpect(jsonPath("$[0].reason").exists())
           .andExpect(jsonPath("$[0].category").exists());
    }
}
