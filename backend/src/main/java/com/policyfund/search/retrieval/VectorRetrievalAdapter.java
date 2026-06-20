package com.policyfund.search.retrieval;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.policyfund.search.dto.Article;
import com.policyfund.search.embedding.ChunkEmbeddingEntity;
import com.policyfund.search.embedding.ChunkEmbeddingRepository;
import com.policyfund.search.embedding.EmbeddingProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 벡터(코사인 유사도) 기반 검색 어댑터. 부모-문서(small-to-big) 전략을 쓴다.
 * (1) 질의를 임베딩해 chunk_embedding 전량과 코사인 유사도로 정렬, 상위 TOP_K 개를 정밀 히트로 뽑고,
 * (2) 각 히트를 문서 내 reading-order 이웃(seq_no ± NEIGHBOR_WINDOW)으로 확장한다.
 * 절차의 각 단계가 별도 청크로 쪼개져 있어도, 한 단계만 히트하면 그 섹션의 연속 청크가 함께 끌려와
 * 합성 LLM 이 전체 절차·목록을 순서대로 재구성할 수 있다. 히트를 먼저 담아 evidence 는 관련도 순을 유지.
 * 또한 한 섹션(문서 + article_no)이 히트를 독점하지 못하도록 섹션당 히트 수를 MAX_PER_SECTION 으로
 * 제한해, 과대표집된 하위 섹션이 정답 섹션을 후보에서 밀어내는 쏠림을 막는다(전체 섹션 본문은 이웃 확장이 회수).
 * 나아가 히트 선정 시 관련도 게이트를 통과한 각 문서에 최소 쿼터(MIN_PER_DOC)를 먼저 배정해, 한 문서가
 * 양적으로 우세해도 다른 문서의 관련 청크가 후보에 들어오도록 보장한다(다문서 커버리지, P1).
 * 브루트포스(MySQL 8.0 호환, VECTOR 미사용), search.retrieval=vector 일 때 활성화.
 */
@Component
@ConditionalOnProperty(name = "search.retrieval", havingValue = "vector")
public class VectorRetrievalAdapter implements RetrievalPort {

    private static final int TOP_K = 40;            // 코사인 점수 상위 정밀 히트 수(섹션 다양화 적용)
    private static final int MAX_PER_SECTION = 6;   // 히트 선정 시 한 섹션(문서 + article_no) 최대 수
    private static final int MIN_PER_DOC = 3;       // 문서 균형: 관련도 게이트 통과 문서당 최소 히트 쿼터(튜닝)
    private static final double RELEVANCE_RATIO = 0.75; // 문서 쿼터 관련도 게이트(최상위 점수 대비, 튜닝)
    private static final int NEIGHBOR_WINDOW = 6;   // 각 히트의 reading-order 이웃 확장 폭(±)
    private static final int MAX_PER_SECTION_FINAL = 18; // 확장 후 최종 후보에서 섹션당 최대 수(재범람 차단)
    private static final int MAX_CANDIDATES = 90;   // 합성기에 넘길 최대 후보 수(컨텍스트 상한)

    private final ChunkEmbeddingRepository repository;
    private final EmbeddingProvider embeddingProvider;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public VectorRetrievalAdapter(ChunkEmbeddingRepository repository, EmbeddingProvider embeddingProvider) {
        this.repository = repository;
        this.embeddingProvider = embeddingProvider;
    }

    @Override
    public List<Article> search(String query) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        float[] queryVector = embeddingProvider.embed(query);
        List<ChunkEmbeddingEntity> all = repository.findAll();

        // (문서, seq_no) -> 청크 인메모리 색인: 이웃 확장을 추가 DB 조회 없이 처리.
        Map<String, ChunkEmbeddingEntity> bySeq = new HashMap<>();
        for (ChunkEmbeddingEntity e : all) {
            bySeq.put(seqKey(e.getDocumentId(), e.getSeqNo()), e);
        }

        // 1) 문서 균형 히트 선정. 코사인 내림차순 정렬 후
        //    Phase 1: 관련도 게이트(top·RELEVANCE_RATIO)를 통과한 각 문서에 MIN_PER_DOC 쿼터 우선 배정,
        //    Phase 2: 남은 자리를 전역 점수 순으로 TOP_K 까지 채움. 둘 다 섹션캡(MAX_PER_SECTION) 준수.
        //    한 문서가 양적으로 우세해 다른 문서의 관련 청크를 후보에서 밀어내는 것을 막는다(다문서 커버리지).
        List<Scored> ranked = all.stream()
                .map(entity -> new Scored(entity, cosine(queryVector, parse(entity.getEmbeddingJson()))))
                .sorted(Comparator.comparingDouble(Scored::score).reversed())
                .toList();
        LinkedHashMap<String, ChunkEmbeddingEntity> hitMap = new LinkedHashMap<>();
        Map<String, Integer> perSection = new HashMap<>();
        if (!ranked.isEmpty()) {
            double floor = ranked.get(0).score() * RELEVANCE_RATIO;
            Map<String, Integer> perDoc = new HashMap<>();
            for (Scored s : ranked) { // Phase 1: 문서별 최소 쿼터(게이트 통과 청크만)
                if (s.score() < floor || hitMap.size() >= TOP_K) {
                    break; // 내림차순이므로 floor 미만이면 이후도 전부 미달.
                }
                if (perDoc.getOrDefault(s.entity().getDocumentId(), 0) >= MIN_PER_DOC) {
                    continue;
                }
                if (tryAddHit(hitMap, perSection, s.entity())) {
                    perDoc.merge(s.entity().getDocumentId(), 1, Integer::sum);
                }
            }
            for (Scored s : ranked) { // Phase 2: 전역 점수로 채움
                if (hitMap.size() >= TOP_K) {
                    break;
                }
                tryAddHit(hitMap, perSection, s.entity());
            }
        }
        List<ChunkEmbeddingEntity> hits = new ArrayList<>(hitMap.values());

        // 2) 히트(관련도 순) 먼저 담고, 그다음 각 히트의 같은 섹션 이웃을 확장(dedup, 상한 적용).
        LinkedHashMap<String, ChunkEmbeddingEntity> picked = new LinkedHashMap<>();
        for (ChunkEmbeddingEntity h : hits) {
            picked.putIfAbsent(h.getChunkId(), h);
        }
        for (ChunkEmbeddingEntity h : hits) {
            if (picked.size() >= MAX_CANDIDATES) {
                break;
            }
            for (int d = 1; d <= NEIGHBOR_WINDOW; d++) {
                addNeighbor(picked, bySeq, h.getDocumentId(), h.getSeqNo() - d);
                addNeighbor(picked, bySeq, h.getDocumentId(), h.getSeqNo() + d);
            }
        }

        // 확장 후에도 한 섹션이 후보를 독점(재범람)하지 못하도록 섹션당 최종 한도를 적용.
        List<Article> candidates = picked.values().stream()
                .map(VectorRetrievalAdapter::toArticle)
                .toList();
        return CandidateMerge.capBySection(candidates, MAX_PER_SECTION_FINAL, MAX_CANDIDATES);
    }

    /** 섹션캡·중복을 지키며 hitMap 에 히트 추가. 추가되면 true. */
    private static boolean tryAddHit(LinkedHashMap<String, ChunkEmbeddingEntity> hitMap,
                                     Map<String, Integer> perSection, ChunkEmbeddingEntity e) {
        if (hitMap.containsKey(e.getChunkId())) {
            return false;
        }
        String section = sectionKey(e);
        if (perSection.getOrDefault(section, 0) >= MAX_PER_SECTION) {
            return false;
        }
        hitMap.put(e.getChunkId(), e);
        perSection.merge(section, 1, Integer::sum);
        return true;
    }

    private static void addNeighbor(LinkedHashMap<String, ChunkEmbeddingEntity> picked,
                                    Map<String, ChunkEmbeddingEntity> bySeq, String documentId, int seqNo) {
        if (seqNo < 0) {
            return;
        }
        ChunkEmbeddingEntity neighbor = bySeq.get(seqKey(documentId, seqNo));
        if (neighbor != null) {
            picked.putIfAbsent(neighbor.getChunkId(), neighbor);
        }
    }

    private static String seqKey(String documentId, int seqNo) {
        return documentId + '#' + seqNo;
    }

    /** 섹션 키: 문서 + article_no(heading). 섹션 다양화 캡의 단위. */
    private static String sectionKey(ChunkEmbeddingEntity e) {
        return e.getDocumentId() + '|' + (e.getArticleNo() == null ? "" : e.getArticleNo());
    }

    private static Article toArticle(ChunkEmbeddingEntity e) {
        return new Article(e.getDocumentId(), e.getFileName(), e.getContentType(),
                e.getArticleNo(), e.getEmbeddingText());
    }

    private float[] parse(String embeddingJson) {
        try {
            return objectMapper.readValue(embeddingJson, float[].class);
        } catch (IOException ex) {
            throw new UncheckedIOException("embedding JSON 파싱 실패", ex);
        }
    }

    /** 코사인 유사도. 길이가 다르거나 영벡터면 0. */
    static double cosine(float[] a, float[] b) {
        if (a == null || b == null || a.length != b.length) {
            return 0.0;
        }
        double dot = 0.0;
        double normA = 0.0;
        double normB = 0.0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            normA += (double) a[i] * a[i];
            normB += (double) b[i] * b[i];
        }
        if (normA == 0.0 || normB == 0.0) {
            return 0.0;
        }
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    private record Scored(ChunkEmbeddingEntity entity, double score) {}
}
