package com.policyfund.search.embedding;

/** 텍스트를 고정 차원 임베딩 벡터로 변환한다. 오프라인 기본 구현은 {@link HashingEmbeddingProvider}. */
public interface EmbeddingProvider {

    /** 입력 텍스트의 임베딩 벡터(길이 == {@link #dimensions()}). */
    float[] embed(String text);

    /** 임베딩 차원 수. */
    int dimensions();
}
