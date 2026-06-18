package com.policyfund.search.ingest;

import com.policyfund.search.embedding.ChunkEmbeddingEntity;
import com.policyfund.search.embedding.ChunkEmbeddingRepository;
import com.policyfund.search.embedding.HashingEmbeddingProvider;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.io.BufferedReader;
import java.io.StringReader;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

/** jsonl 적재: blank/공백 embedding_text skip, dim/embeddingJson/article_no 파생 검증(Docker 불필요). */
class ChunkIngestServiceTest {

    private final HashingEmbeddingProvider embeddingProvider = new HashingEmbeddingProvider();
    private final ChunkEmbeddingRepository repository = mock(ChunkEmbeddingRepository.class);
    private final ChunkIngestService service = new ChunkIngestService(embeddingProvider, repository);

    @Test
    void ingestsValidRecordsAndSkipsBlankEmbeddingText() {
        String jsonl = String.join("\n",
                // heading_path 로 article_no 파생
                "{\"chunk_id\":\"c1\",\"document_id\":\"d1\",\"content_type\":\"text\","
                        + "\"embedding_text\":\"정책자금 융자 신청 서류 제출 기한\","
                        + "\"metadata\":{\"file_name\":\"공고.pdf\",\"page_no\":3,"
                        + "\"heading_path\":[\"제1장\",\"제3조\"]}}",
                // 빈 줄 skip
                "",
                // embedding_text 공백 -> skip
                "{\"chunk_id\":\"c2\",\"document_id\":\"d1\",\"content_type\":\"text\","
                        + "\"embedding_text\":\"   \",\"metadata\":{\"file_name\":\"공고.pdf\",\"page_no\":4}}",
                // heading_path 없음 -> page_no 로 파생
                "{\"chunk_id\":\"c3\",\"document_id\":\"d1\",\"content_type\":\"list-item\","
                        + "\"embedding_text\":\"신청 자격 요건 안내\","
                        + "\"metadata\":{\"file_name\":\"공고.pdf\",\"page_no\":7,\"heading_path\":[]}}");

        int count = service.ingestJsonl(new BufferedReader(new StringReader(jsonl)));

        assertThat(count).isEqualTo(2);

        ArgumentCaptor<ChunkEmbeddingEntity> captor = ArgumentCaptor.forClass(ChunkEmbeddingEntity.class);
        verify(repository, times(2)).save(captor.capture());
        List<ChunkEmbeddingEntity> saved = captor.getAllValues();

        ChunkEmbeddingEntity first = saved.get(0);
        assertThat(first.getChunkId()).isEqualTo("c1");
        assertThat(first.getDim()).isEqualTo(256);
        assertThat(first.getEmbeddingJson()).isNotBlank();
        assertThat(first.getFileName()).isEqualTo("공고.pdf");
        assertThat(first.getArticleNo()).isEqualTo("제1장 > 제3조");

        ChunkEmbeddingEntity second = saved.get(1);
        assertThat(second.getChunkId()).isEqualTo("c3");
        assertThat(second.getArticleNo()).isEqualTo("p.7");
        assertThat(second.getDim()).isEqualTo(256);
    }
}
