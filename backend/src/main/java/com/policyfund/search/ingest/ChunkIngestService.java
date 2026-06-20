package com.policyfund.search.ingest;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.policyfund.search.embedding.ChunkEmbeddingEntity;
import com.policyfund.search.embedding.ChunkEmbeddingRepository;
import com.policyfund.search.embedding.EmbeddingProvider;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * pipeline 의 chunks.jsonl 한 줄당 한 레코드를 읽어 임베딩을 계산하고 chunk_embedding 에 적재한다.
 * chunk_id 가 PK 이므로 save 는 upsert(멱등)다. embedding_text 가 비면 건너뛴다.
 */
@Service
public class ChunkIngestService {

    private final EmbeddingProvider embeddingProvider;
    private final ChunkEmbeddingRepository repository;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ChunkIngestService(EmbeddingProvider embeddingProvider, ChunkEmbeddingRepository repository) {
        this.embeddingProvider = embeddingProvider;
        this.repository = repository;
    }

    /** 파일 경로의 jsonl 을 적재한다. 적재된 레코드 수를 반환. */
    public int ingestFile(Path jsonlPath) {
        try (BufferedReader reader = Files.newBufferedReader(jsonlPath, StandardCharsets.UTF_8)) {
            return ingestJsonl(reader);
        } catch (IOException e) {
            throw new UncheckedIOException("chunks.jsonl 적재 실패: " + jsonlPath, e);
        }
    }

    /** reader 의 jsonl 을 적재한다. 빈 줄·embedding_text 공백 레코드는 건너뛰고 적재 수를 반환. */
    public int ingestJsonl(BufferedReader reader) {
        int count = 0;
        try {
            String line;
            // seq_no: 적재되는(=DB 에 들어가는) 청크에만 문서 내 0-based 순번을 reading order 로 부여한다.
            // 건너뛴 레코드는 순번을 소비하지 않아 DB 행끼리 연속 seq 를 유지(이웃 확장이 정확).
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                JsonNode record = objectMapper.readTree(line);
                String embeddingText = text(record.get("embedding_text"));
                if (embeddingText == null || embeddingText.isBlank()) {
                    continue;
                }
                ChunkEmbeddingEntity entity = toEntity(record, embeddingText, count);
                repository.save(entity);
                count++;
            }
        } catch (IOException e) {
            throw new UncheckedIOException("chunks.jsonl 파싱 실패", e);
        }
        return count;
    }

    private ChunkEmbeddingEntity toEntity(JsonNode record, String embeddingText, int seqNo) throws IOException {
        String chunkId = text(record.get("chunk_id"));
        String documentId = text(record.get("document_id"));
        String contentType = text(record.get("content_type"));
        JsonNode metadata = record.get("metadata");
        String fileName = metadata != null ? text(metadata.get("file_name")) : null;
        String articleNo = deriveArticleNo(metadata);

        float[] vector = embeddingProvider.embed(embeddingText);
        String embeddingJson = objectMapper.writeValueAsString(vector);

        return new ChunkEmbeddingEntity(chunkId, documentId, fileName, contentType, articleNo,
                embeddingText, embeddingJson, vector.length, seqNo, LocalDateTime.now());
    }

    /** heading_path 를 " > " 로 합쳐 article_no 로 쓰고, 없으면 "p."+page_no. */
    private static String deriveArticleNo(JsonNode metadata) {
        if (metadata == null) {
            return null;
        }
        JsonNode headingPath = metadata.get("heading_path");
        if (headingPath != null && headingPath.isArray() && !headingPath.isEmpty()) {
            List<String> parts = new ArrayList<>();
            for (JsonNode node : headingPath) {
                String value = text(node);
                if (value != null && !value.isBlank()) {
                    parts.add(value);
                }
            }
            if (!parts.isEmpty()) {
                return String.join(" > ", parts);
            }
        }
        JsonNode pageNo = metadata.get("page_no");
        if (pageNo != null && !pageNo.isNull()) {
            return "p." + pageNo.asText();
        }
        return null;
    }

    private static String text(JsonNode node) {
        return (node == null || node.isNull()) ? null : node.asText();
    }
}
