package com.policyfund.notices;

import com.policyfund.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@AutoConfigureMockMvc
class NoticeApiIntegrationTest extends AbstractIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getNotice_returnsSeededCategory() throws Exception {
        mvc.perform(get("/api/v1/notices/regulation"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.key").value("regulation"))
           .andExpect(jsonPath("$.label").value("공고"))
           .andExpect(jsonPath("$.docType").value("공고"))
           .andExpect(jsonPath("$.versions").isArray());
    }

    @Test
    void getNotice_unknownCategory_returns404() throws Exception {
        mvc.perform(get("/api/v1/notices/unknown"))
           .andExpect(status().isNotFound())
           .andExpect(jsonPath("$.code").exists());
    }

    @Test
    void registerRevision_thenAppearsAsLatest() throws Exception {
        String body = """
            {"effectiveDate":"2026-03-01",
             "blocks":[{"type":"text","text":"개정 본문"}]}
            """;

        mvc.perform(post("/api/v1/notices/reference/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.version").value("v1"))
           .andExpect(jsonPath("$.date").value("2026-03-01"))
           .andExpect(jsonPath("$.blocks[0].type").value("text"));

        String body2 = """
            {"effectiveDate":"2026-04-01",
             "blocks":[{"type":"text","text":"두번째 개정"}]}
            """;
        mvc.perform(post("/api/v1/notices/reference/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body2))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.version").value("v2"));

        mvc.perform(get("/api/v1/notices/reference"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.versions[0].version").value("v2"));
    }

    @Test
    void registerRevision_backdatedEffectiveDate_returns400() throws Exception {
        // 최신본보다 이른 시행일로는 등록할 수 없다(개정본은 항상 새 최신본).
        mvc.perform(post("/api/v1/notices/datetest/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"effectiveDate\":\"2026-05-01\",\"blocks\":[{\"type\":\"text\",\"text\":\"최신본\"}]}"))
           .andExpect(status().isCreated());

        mvc.perform(post("/api/v1/notices/datetest/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"effectiveDate\":\"2026-04-01\",\"blocks\":[{\"type\":\"text\",\"text\":\"과거 시행일\"}]}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("INVALID_EFFECTIVE_DATE"));
    }

    @Test
    void registerRevision_missingEffectiveDate_returns400() throws Exception {
        mvc.perform(post("/api/v1/notices/reference/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"blocks\":[{\"type\":\"text\",\"text\":\"x\"}]}"))
           .andExpect(status().isBadRequest());
    }

    @Test
    void diff_betweenVersions_marksAddAndSame() throws Exception {
        mvc.perform(post("/api/v1/notices/difftest/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"effectiveDate\":\"2026-05-01\",\"blocks\":[{\"type\":\"text\",\"text\":\"공통\"}]}"))
           .andExpect(status().isCreated());

        String v2Response = mvc.perform(post("/api/v1/notices/difftest/revisions")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"effectiveDate\":\"2026-06-01\",\"blocks\":[{\"type\":\"text\",\"text\":\"공통\"},{\"type\":\"text\",\"text\":\"추가됨\"}]}"))
           .andExpect(status().isCreated())
           .andReturn().getResponse().getContentAsString();

        // Extract the actual version assigned (robust against shared-container state)
        String assignedVersion = com.jayway.jsonpath.JsonPath.read(v2Response, "$.version");

        mvc.perform(get("/api/v1/notices/difftest/versions/" + assignedVersion + "/diff"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$[0].type").value("same"))
           .andExpect(jsonPath("$[1].type").value("add"))
           .andExpect(jsonPath("$[1].block.text").value("추가됨"));
    }

    @Test
    void diff_unknownVersion_returns404() throws Exception {
        mvc.perform(get("/api/v1/notices/difftest/versions/v999/diff"))
           .andExpect(status().isNotFound());
    }
}
