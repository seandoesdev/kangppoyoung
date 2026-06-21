package com.policyfund.notices.dto;

import java.util.List;

public record NoticeCategoryDto(String key, String label, String docType, String docTitle, List<NoticeVersionDto> versions) {}
