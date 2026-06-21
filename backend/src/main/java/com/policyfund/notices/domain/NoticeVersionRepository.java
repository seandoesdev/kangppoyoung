package com.policyfund.notices.domain;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface NoticeVersionRepository extends JpaRepository<NoticeVersionEntity, Long> {

    List<NoticeVersionEntity> findByCategoryKeyOrderByDateDescVersionDesc(String categoryKey);

    /** 정렬 없이 카테고리의 모든 버전. 정렬은 서비스에서 (시행일, 버전번호) 기준으로 일원화한다. */
    List<NoticeVersionEntity> findByCategoryKey(String categoryKey);

    Optional<NoticeVersionEntity> findByCategoryKeyAndVersion(String categoryKey, String version);
}
