package com.policyfund.search.retrieval;

import com.policyfund.search.dto.Article;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/** 후보 병합: dedup·섹션당 한도·전체 한도 검증(Docker 불필요). */
class CandidateMergeTest {

    private Article art(String doc, String section, String text) {
        return new Article(doc, doc + ".pdf", "text", section, text);
    }

    @Test
    void mergeAndCap_dedupsAndCapsPerSection() {
        List<Article> hop1 = new ArrayList<>();
        for (int i = 0; i < 10; i++) {
            hop1.add(art("dA", "S", "t" + i)); // 한 섹션 과대표집
        }
        hop1.add(art("dB", "T", "tb"));
        List<Article> hop2 = List.of(art("dA", "S", "t0"), art("dC", "U", "tc")); // t0 중복, dC 신규

        List<Article> merged = CandidateMerge.mergeAndCap(hop1, hop2, 3, 100);

        // 중복(dA|t0)은 한 번만.
        long t0 = merged.stream().filter(a -> "dA".equals(a.docId()) && "t0".equals(a.text())).count();
        assertThat(t0).isEqualTo(1);
        // 과대표집 섹션 dA|S 는 3개로 제한.
        long dAS = merged.stream().filter(a -> "dA".equals(a.docId()) && "S".equals(a.articleNo())).count();
        assertThat(dAS).isEqualTo(3);
        // 과소표집 섹션(dB, dC)도 포함.
        assertThat(merged).anyMatch(a -> "dB".equals(a.docId()));
        assertThat(merged).anyMatch(a -> "dC".equals(a.docId()));
    }

    @Test
    void interleave_recoversSecondOnlyChunkWithinTightCap() {
        List<Article> first = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            first.add(art("dA", "S", "a" + i)); // 분석기 확장 질의: 한 섹션 다수
        }
        List<Article> second = List.of(art("dKey", "K", "key")); // 원 질의에만 있는 핵심 청크

        // 2:1 우대 + 총 4 한도. first-우선 병합이면 key 가 잘리지만, 교차는 상단에 둬 회수한다.
        List<Article> merged = CandidateMerge.interleave(first, second, 2, 10, 4);

        assertThat(merged).hasSize(4);
        assertThat(merged).anyMatch(a -> "dKey".equals(a.docId()));               // 한쪽에만 있어도 회수
        assertThat(merged.stream().filter(a -> "dA".equals(a.docId())).count()).isEqualTo(3); // 2:1 우대
    }

    @Test
    void capBySection_respectsTotalCap() {
        List<Article> articles = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
            articles.add(art("d" + i, "s", "t" + i)); // 서로 다른 섹션 50개
        }
        assertThat(CandidateMerge.capBySection(articles, 10, 20)).hasSize(20);
    }
}
