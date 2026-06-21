package com.policyfund.notices.asset;

/** 자산 업로드 응답: 콘텐츠 주소 id 와 서빙 URL(/api/v1/notices/assets/{id}). */
public record AssetRef(String id, String url) {}
