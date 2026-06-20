# 구현 계획 — 채팅 기록 좌측 사이드바 노출

통합 검색의 **질의→답변 기록(단일턴 Q&A)** 을 "채팅 기록"으로 좌측 사이드바에 노출한다. 어느 화면에서든
과거 대화를 보고, 클릭 한 번으로 답변을 복원하며, 항목별/전체 삭제할 수 있게 한다.

> 별도 채팅 기능은 없으며, 통합 검색(자연어 질의→gpt-4o 답변)이 유일한 대화형 화면이다. 각 기록 항목 =
> **질문 1개 + 답변 1개**(멀티턴 스레드 아님).

> **갱신(2026-06-20)**: 식별·URL을 `?q=&id=`(쿼리스트링) → **경로 `/q/<sessionId>`(UUIDv4)** 로 변경.
> 백엔드에 `session_id` 컬럼(마이그레이션 `V5`, 기존 행은 백필) + 단건 조회 `GET /search/history/{sessionId}`(404 가능) +
> 삭제 `DELETE /search/history/{sessionId}`(멱등 204) 신설. 신규 행은 앱에서 `UUID.randomUUID()`(v4) 부여.
> 프론트: 라우트 `/q/:sessionId`, 사이드바 클릭→`navigate('/q/<sessionId>')`, 새 검색은 POST 후 생성된 세션으로 이동,
> 딥링크/새로고침은 적재 목록에 없으면 단건 조회로 복원.

## 확정 결정 (사용자)

| 항목 | 결정 |
|------|------|
| 데이터 출처 | 백엔드 `GET /api/v1/search/history`(이미 `result`까지 영속) 단일 진실 출처 |
| 목록 공유 | 신규 React Context `SearchHistoryProvider` (Sidebar·Search 공유) |
| 선택 전달 | **경로 `/q/<sessionId>`** (UUIDv4, 새로고침·딥링크·공유 생존) |
| 노출 개수 | **무한 스크롤 페이지네이션** — `page`/`size`로 스크롤 시 추가 로드 |
| 삭제 기능 | **항목별 삭제 + 전체 지우기** → ⚠️ 백엔드 DELETE 엔드포인트 신설 |
| 전역 기록 | 현 상태 허용(데모/내부용). 사용자 스코프는 후속 과제 |
| 재클릭 | 캐시된 답변 즉시 복원(재질의 0회). nonce 불필요 |

> 항목 표시는 **중복 제거 없이 각 기록 row 를 개별 항목으로** 노출한다(각 row = 고유 id, 삭제 단위).
> 동일 질의가 반복되면 별개 대화로 쌓이며, 이는 채팅 기록 성격과 일치하고 항목별 삭제와도 정합적이다.

---

## 현황

- **백엔드 검색 기록 영속·페이지네이션 완비** — `GET /search/history?page&size` 가
  `SearchHistoryItem(id, query, createdAt, result?)` 반환. `SearchHistoryEntity`(id=Long)/`Repository`
  (`JpaRepository`, `findAllByOrderByCreatedAtDesc`). POST `/search` 시 자동 저장, 응답에 `result` 포함.
  - **삭제 엔드포인트는 없음** → 이번에 신설.
- **프론트 api 배선됨, 미사용** — `api/search.ts` `listSearchHistory()`, `types.ts` `SearchHistoryItem`.
- **프론트 기록은 `Search.tsx` 로컬 state 뿐** — 휘발성, 페이지 하단 표시. → 제거하고 사이드바로 승격.
- **`Sidebar.tsx`** — 접이식 그룹 패턴(`useState open`) 존재, 재사용.
- **레이아웃** — `App.tsx`에서 `Sidebar`는 `<Routes>` 바깥 1회 마운트(유지), `Search`는 라우트별 마운트.

## 구현

### 백엔드 (DELETE 엔드포인트 신설)

| 파일 | 변경 |
|------|------|
| `search/web/SearchController.java` | `DELETE /history/{id}`(204), `DELETE /history`(204) 매핑 추가 |
| `search/service/SearchService.java` | `deleteHistory(long id)`=`repo.deleteById`, `clearHistory()`=`repo.deleteAllInBatch` |
| `search/domain/SearchHistoryRepository.java` | 변경 없음(`JpaRepository` 기본 메서드 사용) |
| `docs/api/openapi.yaml` | 두 DELETE 오퍼레이션 문서화(전담 에이전트) |

- `deleteById` 는 미존재 id 를 조용히 무시 → DELETE 멱등. `deleteAllInBatch` 로 전체를 단일 DELETE.

### 프론트엔드

| 파일 | 변경 |
|------|------|
| `api/search.ts` | `deleteSearchHistory(id)`·`clearSearchHistory()` 추가(`http.delete`). `listSearchHistory` 기존 |
| `context/SearchHistoryContext.tsx` | **신규** Provider + `useSearchHistory` |
| `main.tsx` | `<BrowserRouter>` 안쪽에서 `<App/>` 를 Provider 로 래핑 |
| `components/Sidebar.tsx` | '채팅 기록' 접이식 그룹: 무한스크롤·항목 클릭(`navigate('/?q=')`)·항목 삭제·전체 지우기 |
| `pages/Search.tsx` | 로컬 history 제거, `?q=` 일원화, getCached 복원/재질의, 성공 후 refresh |

**Context API**: `{ items, loading, error, hasMore, loadMore, refresh, remove(id), clear, getCached(query) }`
- 마운트 시 page 0(size 20) 적재. `loadMore`: 다음 page append, `hasMore = batch.length===size`.
  `refresh`: page 0 리셋(새 검색 후 최신 반영). `remove`: `deleteSearchHistory` 후 낙관적 제거.
  `clear`: `clearSearchHistory` 후 비움. `getCached`: items 중 query 일치 + result 존재 최신 항목 result.
- StrictMode 이중 effect 는 `loadingRef` 가드 + 멱등으로 무해.

**Sidebar 무한 스크롤**: 스크롤 컨테이너(`max-h` + `overflow-y-auto`) 하단 sentinel 을 IntersectionObserver
(root=컨테이너)로 관찰 → 교차 시 `loadMore`. 짧은 목록 대비 items 변동 시 재관찰. 각 항목은 질의 button +
삭제(×) button, 활성 표시 `pathname==='/' && q===item.query`. 하단 '전체 지우기'(window.confirm).

**Search `?q=` 흐름**: 입력 Enter·검색 버튼·예시 클릭을 모두 `setSearchParams({q})` 로 일원화.
`useEffect([searchParams,...])` 에서 `q` 추출 → `getCached(q)` 히트면 `setResult`(재질의 0), 미스면
`runSearch(q)`(성공 시 `setResult`+`refresh()`). `runSearch` 는 `busyRef` 가드로 안정 identity 유지.

## 검증

- 빌드: 백엔드 `./gradlew compileJava`(+가능 시 test), 프론트 `npm run build`(tsc).
- 수동: 검색→사이드바 즉시 반영 / 항목 클릭→재질의 없이 복원(네트워크 `/search` 0회) / 결과 새로고침→`?q`+`GET /history` 복원 /
  URL 공유 / 타 라우트에서 클릭→'/'로 이동 표시 / 스크롤 추가 로드 / 항목 삭제·전체 지우기 / StrictMode 멱등.
- 리뷰: 변경 diff 적대적 코드리뷰.

## 리스크

- **전역 기록** — 사용자 스코프 없음(허용 결정). 전체 지우기는 **모든 사용자 기록 삭제**임에 유의(confirm 필수).
- **기록 중복 누적** — 동일 질의도 매 검색마다 row 누적(중복 제거 없이 노출하기로 결정). 서버측 정리는 후속.
- **초기 1-RTT** — 첫 진입 시 `GET /history` 전까지 비어 보임(loading 처리).
- **effect/URL 동기화** — `q` 단일 source 강제, effect 의존성·`busyRef` 가드로 중복/루프 방지.
- **무한 스크롤 재관찰** — 컨테이너보다 짧은 목록에서 IO 재발화 안 되는 케이스 → items 변동 시 재관찰로 보완.
- **StrictMode 이중 effect(dev)** — fetch/검색 2회 호출 가능(멱등, `loadingRef`/`busyRef` 가드).

## 후속 과제 (범위 밖)

- 사용자 스코프(인증·사용자별 기록 격리) — 백엔드 재설계 필요.
- 서버측 동일 질의 dedup / 보존 정책.
