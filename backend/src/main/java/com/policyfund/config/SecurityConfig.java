package com.policyfund.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    /**
     * 1차: 전 엔드포인트 permitAll. API는 무상태이므로 CSRF 비활성.
     * 추후 인증/RBAC 도입 시 아래 분류대로 권한을 부여한다(PRD §9 보안).
     */
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                // 변경성(고위험) — 추후 hasRole("ADMIN")
                //   POST /api/v1/notices/*/revisions
                //   POST /api/v1/notices/*/revisions/preprocess
                // 변경성 — 추후 hasRole("MANAGER")
                //   POST/DELETE /api/v1/search/examples/**
                // 민감 조회 — 추후 hasRole("MANAGER")
                //   GET /api/v1/search/history
                .anyRequest().permitAll()
            );
        return http.build();
    }
}
