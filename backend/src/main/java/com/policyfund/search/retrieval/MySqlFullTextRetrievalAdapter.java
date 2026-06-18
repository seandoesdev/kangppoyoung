package com.policyfund.search.retrieval;

import com.policyfund.search.domain.ArticleEntity;
import com.policyfund.search.domain.ArticleRepository;
import com.policyfund.search.dto.Article;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
@ConditionalOnProperty(name = "search.retrieval", havingValue = "fulltext", matchIfMissing = true)
public class MySqlFullTextRetrievalAdapter implements RetrievalPort {

    private final ArticleRepository articles;

    public MySqlFullTextRetrievalAdapter(ArticleRepository articles) {
        this.articles = articles;
    }

    @Override
    public List<Article> search(String query) {
        return articles.searchFullText(query).stream()
                .map(a -> new Article(a.getDocId(), a.getDocTitle(), a.getDocType(), a.getArticleNo(), a.getText()))
                .toList();
    }
}
