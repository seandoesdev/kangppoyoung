package com.policyfund.search.embedding;

import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Spring AI {@link EmbeddingModel}(OpenAI starter) 기반 임베딩 제공자.
 * search.embedding.provider=openai 일 때만 활성화되며 OPENAI_API_KEY 가 필요하다(온라인).
 * 기본은 오프라인 {@link HashingEmbeddingProvider}.
 */
@Component
@ConditionalOnProperty(name = "search.embedding.provider", havingValue = "openai")
public class OpenAiEmbeddingProvider implements EmbeddingProvider {

    private final EmbeddingModel embeddingModel;

    public OpenAiEmbeddingProvider(EmbeddingModel embeddingModel) {
        this.embeddingModel = embeddingModel;
    }

    @Override
    public float[] embed(String text) {
        return embeddingModel.embed(text);
    }

    @Override
    public int dimensions() {
        return embeddingModel.dimensions();
    }
}
