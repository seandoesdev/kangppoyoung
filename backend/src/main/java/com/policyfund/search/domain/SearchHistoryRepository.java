package com.policyfund.search.domain;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface SearchHistoryRepository extends JpaRepository<SearchHistoryEntity, Long> {
    Page<SearchHistoryEntity> findAllByOrderByCreatedAtDesc(Pageable pageable);

    Optional<SearchHistoryEntity> findBySessionId(String sessionId);
}
