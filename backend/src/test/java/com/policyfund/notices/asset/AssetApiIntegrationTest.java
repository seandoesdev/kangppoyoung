package com.policyfund.notices.asset;

import com.policyfund.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@AutoConfigureMockMvc
class AssetApiIntegrationTest extends AbstractIntegrationTest {

    @Autowired
    MockMvc mvc;

    private byte[] pngBytes() throws Exception {
        java.awt.image.BufferedImage img =
                new java.awt.image.BufferedImage(2, 2, java.awt.image.BufferedImage.TYPE_INT_RGB);
        var out = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(img, "png", out);
        return out.toByteArray();
    }

    @Test
    void upload_image_returnsContentAddressedRef() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "shot.png", "image/png", pngBytes());

        mvc.perform(multipart("/api/v1/notices/assets").file(file))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.id").value(org.hamcrest.Matchers.matchesPattern("[0-9a-f]{64}")))
           .andExpect(jsonPath("$.url").value(org.hamcrest.Matchers.startsWith("/api/v1/notices/assets/")));
    }

    @Test
    void upload_nonImage_returns400() throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "x.txt", "text/plain", "hi".getBytes());

        mvc.perform(multipart("/api/v1/notices/assets").file(file))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("INVALID_FILE_TYPE"));
    }
}
