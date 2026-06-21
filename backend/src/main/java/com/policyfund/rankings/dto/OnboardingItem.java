package com.policyfund.rankings.dto;

public record OnboardingItem(
        int order,
        String category,
        String questionExample,
        String answer,
        String reason,
        int searchCount,
        int viewCount) {}
