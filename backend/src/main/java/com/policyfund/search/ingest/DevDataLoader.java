package com.policyfund.search.ingest;

import com.policyfund.search.embedding.ChunkEmbeddingRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Stream;

/**
 * 부팅 시 chunk_embedding 이 비어 있으면 작업 디렉터리의 out/**\/chunks.jsonl 을 적재한다.
 * search.ingest.on-startup=true 일 때만 활성화(테스트 기본값은 비활성).
 */
@Component
@ConditionalOnProperty(name = "search.ingest.on-startup", havingValue = "true")
public class DevDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(DevDataLoader.class);

    private final ChunkEmbeddingRepository repository;
    private final ChunkIngestService ingestService;

    public DevDataLoader(ChunkEmbeddingRepository repository, ChunkIngestService ingestService) {
        this.repository = repository;
        this.ingestService = ingestService;
    }

    @Override
    public void run(String... args) {
        long existing = repository.count();
        if (existing > 0) {
            log.info("chunk_embedding 이미 {}건 적재됨 — 자동 적재 건너뜀", existing);
            return;
        }
        Path outDir = Paths.get("out");
        if (!Files.isDirectory(outDir)) {
            log.warn("out/ 디렉터리가 없어 chunks.jsonl 자동 적재 건너뜀 (cwd={})", Paths.get("").toAbsolutePath());
            return;
        }
        List<Path> jsonlFiles;
        try (Stream<Path> walk = Files.walk(outDir)) {
            jsonlFiles = walk.filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().equals("chunks.jsonl"))
                    .toList();
        } catch (IOException e) {
            log.error("out/ 탐색 실패 — chunks.jsonl 자동 적재 건너뜀", e);
            return;
        }
        int total = 0;
        for (Path jsonl : jsonlFiles) {
            int ingested = ingestService.ingestFile(jsonl);
            total += ingested;
            log.info("적재 {}건 <- {}", ingested, jsonl);
        }
        log.info("chunk_embedding 자동 적재 완료: 파일 {}개, 총 {}건", jsonlFiles.size(), total);
    }
}
