package com.policyfund.search.embedding;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/** chunk_embedding 저장소. 브루트포스 코사인 검색을 위해 findAll() 로 전량 로드한다. */
public interface ChunkEmbeddingRepository extends JpaRepository<ChunkEmbeddingEntity, String> {

    List<ChunkEmbeddingEntity> findByDocumentId(String documentId);
}
