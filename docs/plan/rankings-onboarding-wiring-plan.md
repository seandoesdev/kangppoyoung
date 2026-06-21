# 구현 플랜 — '질문 분석'(UC-4) · '온보딩 가이드'(UC-5) 백엔드 연동

> 기준: [`docs/prd/PRD.md`](../prd/PRD.md) UC-4/UC-5 + [`docs/user_flow/user_flow.md`](../user_flow/user_flow.md) UC-4/UC-5.
> 두 기능은 **같은 백엔드 모듈(`rankings/`)** 위에 있고 온보딩 커리큘럼이 랭킹에서 그대로 파생되므로, **하나의 플랜으로 함께 구현**한다.
> 목표: 화면만 완성되고 목 데이터로 도는 **질문 분석(`/ranking`)·온보딩 가이드(`/onboarding`)** 두 페이지를 **실제 백엔드와 end-to-end로 연동**한다.

화면 제목 매핑(혼동 주의): **"질문 분석" 페이지 = `Ranking.tsx`**(라우트 `/ranking`), **"온보딩 가이드" 페이지 = `Onboarding.tsx`**(라우트 `/onboarding`).

---

## 1. 현재 상태 (사전 스캔 결과)

### 백엔드 — 완비·실동작 (신규 구현 거의 없음)

- **`GET /api/v1/rankings?period=`** (period **필수**, 누락 시 400). → `List<RankingItem>{rank, category, questionExample, searchCount, viewCount, trend, relatedArticles}`.
  - `RankingService.rankings(period)`(@Transactional): `ranking_cache` **hit/miss**. miss 시 `SearchHistoryRepository.findAll()` 전수 조회 → `createdAt > now-days(period)` 필터 → `OpenAiQuestionCategorizer.categorize(질의들)`로 카테고리 그룹화 → 그룹별 빈도 카운트 → `deleteByPeriod`+`saveAll`로 캐시 재적재. `days()`는 period 문자열에 `"7"` 포함이면 7일, 아니면 30일. 정렬은 `searchCount DESC, viewCount DESC`.
- **`GET /api/v1/onboarding?period=`** (선택, **기본 `'최근 30일'`**). → `List<OnboardingItem>{order, category, reason, searchCount, viewCount, relatedArticles}`.
  - `OnboardingService.onboarding(period)`: **`RankingService.rankings(period)`에 그대로 위임**(별도 추천 로직 없음) → `rank→order`, `reason="실무자 검색 N회·조회 M회로 우선순위가 높습니다."` 생성.
- 통합테스트 존재(`rankings` 패키지, `QuestionCategorizer` 목 주입).
- **플레이스홀더(의도된 미완, PRD §12 보류):** `RankingService`에서 **`viewCount = searchCount`**(동일값 하드코딩), **`trend = "same"`**(항상 동일). 실 조회수/추세 산출 로직 없음.
- **⚠️ 오프라인 공백(가장 중요):** 검색 모듈은 모든 온라인 컴포넌트를 `@ConditionalOnProperty(search.synth.provider=openai)`로 게이트하고 `Offline*` 짝을 둔다(`OfflineQueryAnalyzer`/`OfflineAnswerSynthesizer`/`OfflineRetrievalRefiner`). **그런데 `OpenAiQuestionCategorizer`만 무조건 `@Component`이고 오프라인 짝이 없다.** 결과: `OPENAI_API_KEY` 없는 오프라인 모드에서 `/rankings`·`/onboarding` 호출이 `categorize()`에서 실패(500)하거나, ChatClient 빈 부재 시 부팅 단계에서 깨질 수 있다 → **프로젝트의 "키 없이 오프라인 모드로 전환" 약속이 이 두 기능에서만 깨진다.**

### 계약 — 이미 3중 일치 (변경 불필요)

- `docs/api/openapi.yaml`(`GET /rankings`·`GET /onboarding`, `RankingItem`/`OnboardingItem`/`Article` 스키마) ↔ 백엔드 DTO ↔ `frontend/src/api/types.ts`가 **필드 단위로 1:1 일치**. 아래 "결정"에서 계약을 바꾸지 않는 한 **openapi 변경 없음**.

### 프론트 — 화면 완성, 백엔드 미연동(목 전용)

- `api/rankings.ts` `getRankings(period)` · `api/onboarding.ts` `getOnboardingGuide(period='최근 30일')` — **구현돼 있으나 호출되지 않는 dead code**.
- `pages/Ranking.tsx`(제목 "질문 분석"): `RANKING_BY_PERIOD/RANKING_PERIODS/RankingItem`(목) 사용. `period` 로컬 state, `max = Math.max(...searchCount)`로 막대 정규화.
- `pages/Onboarding.tsx`: 목 `RankingItem`을 `rank` 정렬해 커리큘럼화. **`reason`을 인라인으로 직접 조립**("검색 N회 · 조회 M회…"), **`done` 진행률은 로컬 `useState`(rank 키)로 새로고침 시 소실**, `대표 질문: questionExample` 렌더.
- 목 심볼 `RANKING_BY_PERIOD`·`RANKING_PERIODS`·목 `RankingItem` 타입은 **이 두 페이지에서만** 사용(grep 확인) → 연동 후 `data/mock.ts`에서 제거 가능.

➡ **"구현"의 본질 = 두 페이지를 목→실 API로 전환 + 로딩/에러/빈상태 UX + 플레이스홀더 정직 표현 + (권장) 오프라인 카테고라이저 추가.** 계약·백엔드 비즈니스 로직 신규는 (오프라인 폴백 외) 없음.

---

## 2. 연동 시 드러나는 불일치/함정 (반드시 처리)

1. **`OnboardingItem ≠ RankingItem`.** OnboardingItem에는 `order`·`reason`이 있고 **`questionExample`·`trend`·`rank`가 없다.** 현재 `Onboarding.tsx`는 `item.rank`(키/배지)·`item.questionExample`(대표 질문)·인라인 reason을 쓰므로 **그대로는 타입/표시가 깨진다.** → `order`를 키/순번으로, `reason`은 **서버 값** 사용, **대표 질문(questionExample) 표시는 제거**.
2. **플레이스홀더 정직성.** `trend`가 항상 `'same'`이라 Ranking의 추세 아이콘이 늘 ➖, `viewCount==searchCount`라 "검색 N · 조회 N"이 항상 동일. 의미 있는 지표인 양 보이지 않게 표현을 조정한다(아래 결정).
3. **빈/0 division 버그.** `rankings=[]`(빈 DB·키 없음·카테고리 0건) 시 Ranking의 `Math.max(...[]) = -Infinity` → 막대 width NaN, Onboarding의 `doneCount/total`(total=0) → NaN. **빈 상태 렌더 + 가드** 필수.
4. **오프라인 미동작.** 위 백엔드 오프라인 공백(키 없으면 두 화면 모두 에러).
5. **로딩/에러 UX 부재.** 두 페이지 모두 `useEffect`/loading/error 없음 → **검색·공고 화면 패턴(`ApiError.message`) 답습**.
6. **period 포맷 정합.** 프론트 고정 periods(`['최근 7일','최근 30일']`)가 백엔드 인식 문자열과 정확히 일치해야 함(현재 일치, `days()`가 `"7"` 부분일치로 판정). 백엔드에 periods 목록 API는 없음 → **프론트 고정 상수 유지**.

---

## 3. 확정 결정 (권장) — 미정 시 아래 기본값으로 진행

| 항목 | 결정(권장) | 근거 / 대안 |
|------|------------|-------------|
| 플랜 구성 | **두 기능 단일 플랜**(본 문서) | 같은 `rankings/` 모듈·온보딩=랭킹 파생·공통 mock 정리 |
| 데이터 출처 | 백엔드 `GET /rankings`·`/onboarding` **단일 진실 출처**, 목 제거 | 다른 화면 연동 플랜과 동일 패턴 |
| 온보딩 항목 모델 | **`OnboardingItem` 그대로 사용** — 대표 질문(questionExample) 표시 **제거**, `reason`은 **서버 값** 사용 | DTO/계약에 questionExample 없음. 추가하려면 3중 동기화+`openapi-schema` 에이전트 필요 → **권장 안 함** |
| 진행률(`done`) | **클라이언트 전용 유지 + `localStorage` 영속**(`order` 키) | 백엔드 영속은 엔드포인트 신설+사용자 스코프 필요 → 후속 |
| `trend` 표현 | 값이 `'up'`/`'down'`일 때만 아이콘 노출, **전부 `'same'`인 동안 추세 표기 숨김** | 항상 ➖는 오인 유발. 실 추세는 후속(§12) |
| `viewCount` 표현 | 현 단계 `searchCount`와 동일하므로 **"조회"를 별도 지표로 강조하지 않음**(동일 표기 또는 "검색 N" 단일 표기) | 실 조회수 추적은 후속(§12) |
| 오프라인 카테고라이저 | **(권장 포함)** `OfflineQuestionCategorizer` 신설 + provider 게이팅 | 키 없이 부팅·테스트·오프라인 동작 보장(프로젝트 약속 정합). **운영을 키 모드로만 한다면 보류 가능** |
| 집계 기간 상수 | 프론트 공용 상수로 이전(목 삭제분 대체) | mock 제거 후 periods 출처 필요 |

> ⚠️ "오프라인 카테고라이저"를 **포함하면** PRD/user_flow의 UC-4 core rule "QuestionCategorizer는 OpenAI 전용·오프라인 폴백 없음"을 **같은 커밋에서 함께 수정**해야 한다(Docs-first). 보류하면 문서·코드 모두 현행 유지.

---

## 4. 범위

**In:** ① `Ranking.tsx`·`Onboarding.tsx` 백엔드 연동(조회·기간 토글 재조회), ② 로딩/에러/빈상태 UX, ③ 플레이스홀더 정직 표현(trend/viewCount), ④ 온보딩 진행률 `localStorage` 영속, ⑤ 미사용 rankings 목 정리, ⑥ **(권장)** 오프라인 카테고라이저 + provider 게이팅, ⑦ 관련 문서 정합(연동 상태 + (포함 시) core rule), ⑧ 빌드·테스트 검증.

**Out(이번 범위 밖 · 후속/§12):** 실 조회수 추적(view 이벤트 수집·테이블·엔드포인트), 실 `trend` 산출(기간 대비 비교), 진행률 백엔드 영속·사용자 스코프·인증, `ranking_cache` TTL/스케줄 재계산, 카테고리 매칭 정확도 개선(substring→임베딩), `relatedArticles` 실제 문서 검증(LLM 환각 방지).

---

## 5. 작업 항목 (체크리스트)

### 5.A (권장·선택) 백엔드 — 오프라인 카테고라이저
- [ ] `rankings/categorize/OpenAiQuestionCategorizer.java`에 `@ConditionalOnProperty(name="search.synth.provider", havingValue="openai")` 부여(검색 모듈 관례와 동일하게 게이트).
- [ ] `rankings/categorize/OfflineQuestionCategorizer.java` **신설** — `implements QuestionCategorizer`, `@ConditionalOnProperty(name="search.synth.provider", havingValue="offline", matchIfMissing=true)`. 결정론적 그룹화(예: 질의 정규화 후 키워드/선두 토큰 버킷팅, 빈 입력→빈 리스트). LLM 의존·외부호출 없음.
- [ ] 결정론 단위테스트(같은 입력 → 같은 `CategoryGroup` 순서/내용). `relatedArticles`는 빈 리스트 또는 결정론적 매핑.
- [ ] (포함 시) `docs/prd/PRD.md`·`docs/user_flow/user_flow.md`의 UC-4 core rule("OpenAI 전용·오프라인 폴백 없음") 수정.

### 5.B 프론트 — '질문 분석' `Ranking.tsx`
- [ ] `../data/mock` import 제거 → `getRankings`(`../api/rankings`), `RankingItem`/`Trend`(`../api/types`) 사용. 기간 상수는 공용 상수(5.D)에서.
- [ ] `useEffect([period])`: `setLoading(true)` → `getRankings(period)` → `setItems`/`catch(ApiError→setError)` → `finally setLoading(false)`. **stale 응답 가드**(period 변경 시 직전 응답 무시 — 취소 플래그).
- [ ] 막대 정규화 가드: `const max = items.length ? Math.max(...items.map(i=>i.searchCount)) : 0;` width는 `max>0 ? (count/max*100) : 0`.
- [ ] 추세 아이콘: `trend!=='same'`일 때만 🔺/🔻 노출(전부 same인 동안 숨김).
- [ ] 조회수 표기: 결정에 따라 "검색 N" 단일 표기 또는 동일값 명시.
- [ ] 로딩(스피너/스켈레톤)·에러(`ApiError.message`)·빈상태("집계된 질문이 없습니다 · 검색 기록이 쌓이면 표시됩니다") 렌더.

### 5.C 프론트 — '온보딩 가이드' `Onboarding.tsx`
- [ ] `../data/mock` import 제거 → `getOnboardingGuide`(`../api/onboarding`), `OnboardingItem`(`../api/types`) 사용.
- [ ] `useEffect([period])`(기본 `'최근 30일'`): `getOnboardingGuide(period)` → `setItems`(로딩/에러/stale 가드 동일).
- [ ] 렌더 매핑 교정: key=`item.order`, STEP/순번=`item.order`, 배지 "학습 N순위"=`order`, **`reason`은 `item.reason`(서버 값) 사용**(인라인 조립 제거), **대표 질문(`questionExample`) 블록 제거**(DTO에 없음), `relatedArticles`는 `ArticleCard` 그대로.
- [ ] 진행률: `done` 키를 `order`로 변경, `localStorage` 영속(키 예: `onboarding:done:<period>` 또는 전역). `doneCount/total` 가드(`total===0 → 0%`).
- [ ] 로딩·에러·빈상태("학습 우선순위를 만들 데이터가 아직 없습니다") 렌더.

### 5.D mock 정리
- [ ] 두 페이지 연동 후 `data/mock.ts`에서 `RANKING_BY_PERIOD`·`RANKING_PERIODS`·목 `RankingItem` 타입 제거(이 두 페이지 외 미사용 확인됨). 다른 목(`NOTICES` 등)·`Article` 타입은 보존.
- [ ] 집계 기간 상수는 공용 상수로 재배치(예: `frontend/src/api/periods.ts`의 `RANKING_PERIODS = ['최근 7일','최근 30일'] as const`, 두 페이지가 import). 백엔드 `days()` 인식 문자열과 일치 유지.

### 5.E 문서/계약
- [ ] `docs/api/openapi.yaml`: 이번 결정에서 계약을 바꾸지 않으므로 **변경 없음**(이미 1:1 일치). 단, 향후 questionExample 추가·진행률 영속을 범위에 넣을 경우에만 `openapi-schema` 전담 에이전트 위임.
- [ ] `docs/prd/PRD.md`·`docs/user_flow/user_flow.md`: 프론트 UC-4/UC-5 상태 `[미연동]→[연동]` 갱신. (오프라인 카테고라이저 포함 시) core rule 동반 수정.
- [ ] `CLAUDE.md`: 최상위/모듈 구조 변경 없음(기존 패키지 내 파일 추가) → **갱신 불필요**.

### 5.F 검증
- [ ] 백엔드: `cd backend && ./gradlew compileJava` (+ 가능 시 `./gradlew test` — rankings 통합테스트는 Testcontainers/Docker 필요). 오프라인 카테고라이저 추가 시 결정론 단위테스트 green.
- [ ] 프론트: `cd frontend && npm run build`(`tsc -b && vite build`) green.
- [ ] 수동(키 모드 / 오프라인 모드 각각): `/ranking`·`/onboarding` 진입 → 데이터 표시 / 기간 토글 재조회 / 빈 DB 빈상태 / 키 없음 시 (폴백 동작 또는) 에러 UX / 온보딩 done 토글 후 새로고침 영속.
- [ ] 변경 diff 적대적 코드리뷰.

---

## 6. 설계 결정·주의

- **온보딩은 랭킹의 파생**(별도 추천 없음) — 백엔드가 이미 그렇게 구현. 프론트도 `OnboardingItem`을 그대로 신뢰하고 `reason`/`order`를 서버 값으로 표시(인라인 재계산 금지).
- **플레이스홀더를 진짜처럼 보이지 않게** — 항상 `'same'`인 추세 아이콘·`searchCount`와 같은 `viewCount`는 사용자를 오인시킨다. 실데이터가 들어오기 전까지 중립/숨김 처리하고, 실 추적은 후속으로 명시.
- **에러 표면화** — 모든 API 호출은 `ApiError(code/message)`를 잡아 사용자 메시지로 표시(흰 화면 회귀 방지, 검색/공고 화면 패턴 답습).
- **결정론·오프라인 정합** — 카테고라이저만 OpenAI 전용이라 프로젝트의 오프라인/테스트 약속을 깬다. 오프라인 짝을 provider 게이팅으로 추가하면 검색 모듈과 일관되고, 키 없이도 부팅·테스트가 결정론적으로 통과.
- **캐시 주의** — `ranking_cache`는 TTL 없이 period 키로 캐시되며 miss 때만 재계산(`deleteByPeriod`+`saveAll`). 새 검색이 즉시 랭킹에 반영되지 않을 수 있음(현 동작 유지, 재계산 전략은 후속).

## 7. 변경 대상 파일

- `frontend/src/pages/Ranking.tsx` (핵심)
- `frontend/src/pages/Onboarding.tsx` (핵심)
- `frontend/src/api/periods.ts` (신규, 공용 기간 상수) — 또는 두 페이지 인라인 상수
- `frontend/src/data/mock.ts` (rankings 목 제거)
- `backend/.../rankings/categorize/OpenAiQuestionCategorizer.java` · `OfflineQuestionCategorizer.java`(신규) — **(권장·선택)**
- `docs/prd/PRD.md` · `docs/user_flow/user_flow.md` (상태 갱신; core rule은 오프라인 폴백 포함 시)
- (openapi.yaml·백엔드 컨트롤러/서비스/DTO·`CLAUDE.md` 변경 없음)

## 8. 리스크

- **OpenAI 비결정성** — 같은 질의도 호출마다 카테고리가 달라져 랭킹/온보딩 순서가 흔들릴 수 있음(캐시가 일부 완화). 오프라인 모드는 결정론.
- **키 부재** — (오프라인 폴백 미포함 시) 키 없으면 두 화면 완전 미동작. 포함 시 결정론 폴백으로 동작.
- **빈/0 division** — 빈 결과에서의 NaN 폭. 가드·빈상태로 차단.
- **플레이스홀더 오인** — trend/viewCount가 의미 있는 지표로 읽힐 위험. 표현 조정으로 차단.
- **캐시 staleness** — TTL 없음. 최신 검색이 즉시 반영 안 될 수 있음(후속).
- **카테고리 substring 매칭 부정확** — 짧은 카테고리/예시에서 과대·과소 카운트 가능(정확도 개선은 후속).

## 9. 후속 과제 (범위 밖)

- 실 조회수 추적(답변/조항 view 이벤트 수집 → `viewCount` 실데이터) · 실 `trend`(기간 대비 비교 산출).
- 온보딩 진행률 백엔드 영속(+ 인증·사용자 스코프) — 엔드포인트·계약 신설 필요.
- `ranking_cache` TTL/스케줄 재계산(예: `@Scheduled` 또는 새 검색 시 무효화).
- 카테고리화 정확도(substring → 임베딩/의미 유사도) · `relatedArticles` 실제 문서 대조 검증.
