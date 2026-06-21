package com.policyfund.notices.service;

import com.policyfund.common.error.BadRequestException;
import com.policyfund.common.error.ResourceNotFoundException;
import com.policyfund.notices.domain.NoticeCategoryEntity;
import com.policyfund.notices.domain.NoticeCategoryRepository;
import com.policyfund.notices.domain.NoticeVersionEntity;
import com.policyfund.notices.domain.NoticeVersionRepository;
import com.policyfund.notices.dto.ContentBlock;
import com.policyfund.notices.dto.DiffBlock;
import com.policyfund.notices.dto.NoticeCategoryDto;
import com.policyfund.notices.dto.NoticeRevisionRequest;
import com.policyfund.notices.dto.NoticeVersionDto;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;

@Service
public class NoticeService {

    private final NoticeCategoryRepository categories;
    private final NoticeVersionRepository versions;

    public NoticeService(NoticeCategoryRepository categories, NoticeVersionRepository versions) {
        this.categories = categories;
        this.versions = versions;
    }

    /** 버전 정렬 기준: 시행일 오름차순, 동일 시행일은 버전번호(숫자) 오름차순. getNotice/diff 가 공유한다. */
    private static final Comparator<NoticeVersionEntity> BY_DATE_THEN_VERSION =
            Comparator.comparing(NoticeVersionEntity::getDate)
                    .thenComparingInt(e -> parseVersionNumber(e.getVersion()));

    @Transactional(readOnly = true)
    public NoticeCategoryDto getNotice(String category) {
        NoticeCategoryEntity cat = categories.findById(category)
                .orElseThrow(() -> new ResourceNotFoundException("NOTICE_CATEGORY_NOT_FOUND",
                        "공고 카테고리를 찾을 수 없습니다: " + category));

        // 최신본이 맨 앞(versions[0]) — (시행일, 버전번호) 내림차순. diff 와 동일 기준을 역순으로 사용한다.
        List<NoticeVersionDto> versionDtos =
                versions.findByCategoryKey(category).stream()
                        .sorted(BY_DATE_THEN_VERSION.reversed())
                        .map(this::toDto)
                        .toList();

        return new NoticeCategoryDto(cat.getKey(), cat.getLabel(), cat.getDocType(), cat.getDocTitle(), versionDtos);
    }

    @org.springframework.transaction.annotation.Transactional
    public NoticeVersionDto registerRevision(String category, NoticeRevisionRequest request) {
        categories.findById(category)
                .orElseThrow(() -> new ResourceNotFoundException("NOTICE_CATEGORY_NOT_FOUND",
                        "공고 카테고리를 찾을 수 없습니다: " + category));

        List<NoticeVersionEntity> existing = versions.findByCategoryKey(category);

        // 개정본은 항상 새 최신본으로 등록한다(과거 시행일 등록 금지). 이 불변식 덕분에 등록 직후
        // 새 버전이 항상 versions[0] 이 되어 프론트가 방금 등록한 최신본을 정확히 가리킨다.
        LocalDate latestDate = existing.stream()
                .map(NoticeVersionEntity::getDate)
                .max(Comparator.naturalOrder())
                .orElse(null);
        if (latestDate != null && request.effectiveDate().isBefore(latestDate)) {
            throw new BadRequestException("INVALID_EFFECTIVE_DATE",
                    "시행일은 현재 최신본(" + latestDate + ") 이후여야 합니다. 과거 시행일로는 등록할 수 없습니다.");
        }

        int next = existing.stream()
                .map(NoticeVersionEntity::getVersion)
                .map(NoticeService::parseVersionNumber)
                .max(Integer::compareTo)
                .orElse(0) + 1;

        var saved = versions.save(new NoticeVersionEntity(
                category, "v" + next, request.effectiveDate(), request.blocks()));

        return toDto(saved);
    }

    @org.springframework.transaction.annotation.Transactional(readOnly = true)
    public List<DiffBlock> diff(String category, String version) {
        List<NoticeVersionEntity> ordered =
                versions.findByCategoryKey(category).stream()
                        .sorted(BY_DATE_THEN_VERSION)
                        .toList();

        int idx = -1;
        for (int k = 0; k < ordered.size(); k++) {
            if (ordered.get(k).getVersion().equals(version)) { idx = k; break; }
        }
        if (idx < 0) {
            throw new ResourceNotFoundException("NOTICE_VERSION_NOT_FOUND",
                    "버전을 찾을 수 없습니다: " + category + "/" + version);
        }

        List<ContentBlock> current = ordered.get(idx).getBlocks();
        List<ContentBlock> previous = idx > 0 ? ordered.get(idx - 1).getBlocks() : List.of();
        return BlockDiff.diff(previous, current);
    }

    private static int parseVersionNumber(String version) {
        try {
            return version.startsWith("v") ? Integer.parseInt(version.substring(1)) : 0;
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private NoticeVersionDto toDto(NoticeVersionEntity e) {
        return new NoticeVersionDto(e.getVersion(), e.getDate(), e.getBlocks());
    }
}
