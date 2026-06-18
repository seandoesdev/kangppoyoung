# 미반영 기능 구현 플랜 (goal-driven, 다중 턴)

> 목표: 스펙 미반영분 구현 + 완전한 테스트 + 프론트↔백엔드↔벡터DB end-to-end.
> 원칙: 결정적·테스트 가능한 수직 슬라이스부터 TDD. offline-first(외부 키/바이너리 불필요).
> 기준선: pipeline pytest 35 passed (2026-06-18).

## 아키텍처 결정 (기본값, offline-first)
- 추출 엔진은 pdfplumber 유지(PyMuPDF 전면 재작성 X — §22 미정사항). OCR/Vision은
  **provider 추상화 + offline 폴백**으로 구조만 확립(필수 바이너리/키 없이 동작).
- 벡터 저장은 기존 **MySQL** 스택 내에 임베딩 테이블로 적재. 임베딩은 기본 **결정적 offline
  해시 임베딩**, `OPENAI_API_KEY` 있으면 OpenAI 임베딩. 외부 벡터DB 서비스 추가 없음.
- 모든 신규 코드 TDD. 각 슬라이스 종료 시 전체 테스트 green + 리뷰 에이전트 검증.

## 진행 체크리스트
### Phase A — 파이프라인 결정적 갭 (no new deps)
- [x] A1. relations: parent_chunk_id 연결(heading prefix + 표 앵커) — DONE, pytest 37 passed
- [ ] A2. relations: 이종 청크 양방향 related(표 note↔row, figure↔step) 결정적 범위
- [ ] A3. tables: 섹션 상속(section_path) 채우기
- [ ] A4. tables: 분할표 cross-page 논리 병합(page_range)
- [ ] A5. config: 스펙 §19 Settings 확장(하위호환), env/CLI 주입
- [ ] A6. 하드닝: max_chunks / max_serialized_mb 가드 + 종료코드 5/4 경로

### Phase B — Provider 추상화(P3 구조) offline-first
- [ ] B1. VisionProvider/OcrProvider 인터페이스 + OfflineProvider(결정적) + cache
- [ ] B2. figures: 이미지→infographic 설명 경로(offline=설명 스텁, 키 있으면 실호출)

### Phase C — 벡터DB 적재 + 백엔드 검색
- [ ] C1. embedding provider(결정적 offline + OpenAI) — backend
- [ ] C2. chunk_embedding 스키마(Flyway V__) + 적재 서비스(jsonl→DB)
- [ ] C3. VectorRetrievalPort + 어댑터(코사인), 검색 라우팅
- [ ] C4. pipeline→backend 브리지(ProcessBuilder, manifest.json 권위) 또는 jsonl 적재 잡

### Phase D — 프론트 연동 + E2E
- [ ] D1. 프론트 검색 UI ↔ 백엔드 /api/v1/search 연동 확인/보완
- [ ] D2. E2E: 프론트 접속→검색→벡터DB 결과 표시
- [ ] D3. 전체 테스트(파이프라인 pytest / 백엔드 gradle test / 프론트 build) green

## 로그
- 2026-06-18: 플랜 수립, 기준선 35 passed 확인. A1 착수.
