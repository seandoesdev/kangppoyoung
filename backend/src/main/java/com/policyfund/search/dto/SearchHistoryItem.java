package com.policyfund.search.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record SearchHistoryItem(String id, String sessionId, String query, Instant createdAt, SearchResult result) {}
