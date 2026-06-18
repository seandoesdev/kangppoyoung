package com.policyfund.search.embedding;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 결정론적·오프라인 해싱 임베딩(hashing trick). 외부 의존성/네트워크 없이
 * 토큰을 256개 버킷으로 폴딩하고 L2 정규화한다. 같은 텍스트 -> 같은 벡터(JVM/실행 무관).
 *
 * String.hashCode 는 JLS 명세상 고정이므로 결정성이 보장된다(Object identity hash 사용 금지).
 * 기본 제공자 빈: search.embedding.provider 가 없거나 "hash" 일 때 활성화.
 */
@Component
@ConditionalOnProperty(name = "search.embedding.provider", havingValue = "hash", matchIfMissing = true)
public class HashingEmbeddingProvider implements EmbeddingProvider {

    private static final int DIM = 256;

    @Override
    public float[] embed(String text) {
        float[] vec = new float[DIM];
        if (text == null || text.isBlank()) {
            return vec;
        }
        // 영숫자(한글 포함)는 토큰으로 유지, 그 외 문자(공백/구두점)는 구분자.
        for (String token : text.toLowerCase().split("[^\\p{IsAlphabetic}\\p{IsDigit}]+")) {
            if (token.isEmpty()) {
                continue;
            }
            int bucket = Math.floorMod(token.hashCode(), DIM);
            vec[bucket] += 1.0f;
        }
        l2Normalize(vec);
        return vec;
    }

    @Override
    public int dimensions() {
        return DIM;
    }

    private static void l2Normalize(float[] vec) {
        double sumSq = 0.0;
        for (float v : vec) {
            sumSq += (double) v * v;
        }
        double norm = Math.sqrt(sumSq);
        if (norm == 0.0) {
            return; // 영벡터 가드: 정규화하지 않는다.
        }
        for (int i = 0; i < vec.length; i++) {
            vec[i] = (float) (vec[i] / norm);
        }
    }
}
