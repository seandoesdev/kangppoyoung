package com.policyfund.search.retrieval;

import com.policyfund.search.domain.ArticleEntity;
import com.policyfund.search.domain.ArticleRepository;
import com.policyfund.search.dto.Article;
import com.policyfund.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

// 이 테스트는 MySQL FULLTEXT 검색 어댑터를 검증한다. 앱 기본값은 vector 이므로 fulltext 로 고정.
@TestPropertySource(properties = "search.retrieval=fulltext")
class ArticleRetrievalIntegrationTest extends AbstractIntegrationTest {

    @Autowired ArticleRepository articles;
    @Autowired RetrievalPort retrieval;

    @Test
    void fullTextSearch_findsArticleByTerm() {
        articles.save(new ArticleEntity("D-100", "지원 규정", "규정", "제5조",
                "신청 서류 제출 기한은 공고일로부터 30일 이내로 한다"));
        articles.save(new ArticleEntity("D-101", "운영 지침", "지침", "제2조",
                "이 지침은 운영 절차를 정한다"));

        List<Article> found = retrieval.search("제출 기한");

        assertThat(found).isNotEmpty();
        assertThat(found).anySatisfy(a -> assertThat(a.text()).contains("제출 기한"));
    }
}
