# 구현 계획 — 검색 기록 좌측 사이드바 노출

검색 기록(검색 페이지 하단의 휘발성 목록)을 **좌측 사이드바 메뉴로 승격**해, 어느 화면에서든 최근
질의를 보고 클릭 한 번으로 결과를 복원할 수 있게 한다.

> 설계 방식: 독립 설계안 3종(백엔드 SoT+URL / 인메모리 Context 미러 / localStorage 전용)을 생성·심사해
> **안1**을 채택했다(적합도 9·단순성 7·정확성 9 = 25점). 새로고침·URL 공유·딥링크·뒤로가기까지 생존하는
> **최고 내구성**, 그리고 이미 존재하는 백엔드/타입 자산 재사용이 결정 근거다.

---

## 현황

- **백엔드는 검색 기록을 이미 완비** — `GET /api/v1/search/history?page&size` 가
  `SearchHistoryItem(id, query, createdAt, result?)` 를 반환하고, `SearchHistoryEntity`/`Repository` 로
  DB 영속한다. POST `/search` 시 query+result 가 자동 저장되며 **응답에 `result` 까지 포함**(캐시 복원 가능).
- **프론트 api 레이어도 배선 완료, 다만 미사용** — `frontend/src/api/search.ts` 의 `listSearchHistory()` 와
  `frontend/src/api/types.ts` 의 `SearchHistoryItem` 이 이미 존재하나 아무 화면도 호출하지 않는다.
- **프론트 기록은 `Search.tsx` 로컬 state 뿐** — 컴포넌트 `useState` 로만 보관(페이지 하단 표시), 네비게이션·
  새로고침 시 소실, 백엔드 미연동.
- **사이드바(`Sidebar.tsx`)에는 기록 항목 없음** — 접이식 그룹 패턴(`useState open`)은 이미 존재해 재사용 가능.
- **레이아웃** — `App.tsx` 에서 `Sidebar` 는 `<Routes>` 바깥에서 1회 마운트되어 유지되고, `Search` 는
  라우트별 mount/unmount 된다 → **크로스-라우트 상태 공유 채널**이 필요하다.

## 채택안 (안1) — 백엔드 SoT + Context(목록) + URL `?q=`(선택)

| 축 | 결정 | 근거 |
|----|------|------|
| **데이터 출처** | 백엔드 `GET /search/history` 단일 진실 출처(SoT) | 이미 `result` 까지 영속, 프론트 계약·타입 재사용으로 신규 엔드포인트/타입 0 |
| **목록 공유** | 신규 React Context `SearchHistoryProvider` | Sidebar·Search 가 동일 인스턴스 구독 |
| **선택 전달** | URL 쿼리파라미터 `?q=` | 새로고침·딥링크·공유·뒤로가기 생존(내구성 1순위) |
| **클릭 동작** | `navigate('/?q=<encoded>')` → 캐시 result 복원, 없으면 재질의 | 백엔드가 result 영속 → 대부분 네트워크 0회 |

**탈락안 요약**: 안2(인메모리 Context 미러, 20점)는 새로고침 시 보던 결과 자체가 소실되고 딥링크/공유 불가.
안3(localStorage 전용, 19점)은 백엔드가 이미 보유한 result 자산을 버리고 클라 중복 저장 → 데이터 이원화·
용량(5MB)·스키마 드리프트·XSS 평문 노출.

### 동작 흐름

1. `SearchHistoryProvider` 가 마운트 시 `listSearchHistory({page:0,size:20})` 1회 fetch → `items` 공급.
2. Sidebar 가 `items` 를 query 기준 dedup 후 상위 N(8)개를 button 으로 렌더.
3. 항목 클릭 → `navigate('/?q=...')`.
4. Search 가 `useSearchParams` 로 `?q` 구독 → `getCached(q)` 히트면 **재질의 없이 복원**, 미스면
   `searchPolicy(q)` 호출 후 `refresh()` 로 사이드바 갱신.
5. 검색 진입점(입력 Enter·검색 버튼·예시 클릭)을 `setSearchParams({q})` 로 **일원화** →
   "검색 = URL 변경 = effect 실행" 단일 흐름.

---

## 구현 단계

1. **신규 `frontend/src/context/SearchHistoryContext.tsx`** — `createContext` + `SearchHistoryProvider`
   + `useSearchHistory` 훅. state: `items: SearchHistoryItem[]`, `loading`, `error`.
   - mount effect(`[]`)에서 `listSearchHistory({page:0,size:20})` 호출(try/catch→error, finally loading).
     StrictMode 이중 effect 대비 `ignore` 플래그 / `AbortController` 가드.
   - 노출: `{ items, loading, error, refresh(): Promise<void>, getCached(query): SearchResult|undefined }`.
     `getCached` 는 query 일치 + `result` 존재하는 최신 항목의 result 반환. Provider 밖 사용 시 throw.
2. **`frontend/src/main.tsx`** — `<BrowserRouter>` 안쪽에서 `<App/>` 를 `<SearchHistoryProvider>` 로 감싼다
   (라우터 컨텍스트 필요 + Sidebar/Search 공통 조상):
   `<StrictMode><BrowserRouter><SearchHistoryProvider><App/></SearchHistoryProvider></BrowserRouter></StrictMode>`.
3. **`frontend/src/components/Sidebar.tsx`** — `useNavigate`·`useSearchParams`·`useSearchHistory` import.
   기존 접이식 그룹 패턴을 복제해 '통합 검색' 아래에 **'검색 기록' 그룹** 추가. query dedup 후 상위 N(8)개를
   button 으로 렌더, `onClick={() => navigate(\`/?q=${encodeURIComponent(item.query)}\`)}`.
   활성 표시: `location.pathname==='/' && searchParams.get('q')===item.query`. 긴 query truncate,
   loading '불러오는 중…', empty '검색 기록 없음'.
4. **`frontend/src/pages/Search.tsx` 로컬 기록 제거** — `HistoryEntry`(16–19), `history` useState(24),
   `runSearch` 내 `setHistory`(44–47), 하단 '검색 기록' 블록(150–169) 전부 삭제.
   `useEffect`·`useSearchParams`·`useSearchHistory` import 추가.
5. **진입점 URL 일원화** — `const [searchParams, setSearchParams] = useSearchParams()`,
   `const { getCached, refresh } = useSearchHistory()`. 입력 Enter·검색 버튼·예시 버튼을 `runSearch` 직접
   호출 대신 `setSearchParams({ q: <trimmed> })` 로 통일. `runSearch` 는 내부 헬퍼로 유지하되 호출은 effect 가 담당.
6. **Search effect** — `useEffect(() => { const q = searchParams.get('q')?.trim(); if(!q) return;
   setQuery(q); const cached = getCached(q); if(cached){ setResult(cached); setError(null); return }
   runSearch(q) }, [searchParams])`. `runSearch(q)`: trim/loading 가드 → `searchPolicy(q)` →
   성공 `setResult(r)` 후 `refresh()` → catch 에러 → finally loading. 동일 q 재클릭(URL 동일)은 캐시 복원
   목적상 재질의 불필요 → effect 미발화가 무해(**nonce 불필요**).
7. **입력 동기화** — 입력창 `value={query}`, `onChange` 는 로컬 `setQuery` 만(타이핑 중 URL 미변경).
   실제 트리거는 5단계 경로로만. 새로고침/딥링크로 `?q` 가 이미 있으면 mount effect 가 한 번 돌아 복원.
8. **수동 검증** — 아래 "검증" 절.
9. **`api/search.ts`·`types.ts` 변경 없음** — `listSearchHistory`·`SearchHistoryItem(result?)` 계약 재사용.

## 변경 파일

| 파일 | 변경 |
|------|------|
| `frontend/src/context/SearchHistoryContext.tsx` | **신규** — Provider + `useSearchHistory`(items/loading/error, refresh, getCached) |
| `frontend/src/main.tsx` | `<BrowserRouter>` 안쪽에서 `<App/>` 를 Provider 로 래핑 |
| `frontend/src/components/Sidebar.tsx` | '검색 기록' 접이식 그룹 추가, button + `navigate('/?q=...')`, 활성 표시 |
| `frontend/src/pages/Search.tsx` | 로컬 history 제거, `?q` 일원화, getCached 복원/재질의 effect |
| `frontend/src/api/search.ts` | 변경 없음(참조만) |
| `frontend/src/api/types.ts` | 변경 없음(`SearchHistoryItem` 재사용) |

**백엔드·신규 라우트·신규 타입·신규 의존성: 0.** 난이도 중(M), 대략 반나절~1일.

## 검증 (수동)

- (a) 검색 → 사이드바 기록 즉시 반영(`refresh`).
- (b) 사이드바 항목 클릭 → 통합검색 이동 + 캐시 result 표시(네트워크 탭 `/search` **0회**).
- (c) 결과 보던 상태에서 새로고침 → URL `?q` + `GET /history` 캐시로 **결과 자체 복원**(안2 대비 핵심 차별점).
- (d) URL 복사·붙여넣기 → 동일 결과(딥링크/공유).
- (e) `/ranking` 등 타 라우트에서 기록 클릭 → '/'로 이동하며 결과 표시.
- (f) StrictMode(dev) 2회 호출이 멱등으로 무해한지 확인.

## 리스크

- **전역 기록** — 백엔드에 인증/사용자 스코프가 없어 모든 사용자 질의가 노출됨(데모/내부용 전제, 해결은 백엔드 변경 필요).
- **기록 중복 증가** — 백엔드가 동일 query 도 매번 새 row 저장. `size=20` + client dedup(by query) + 상위 N 제한으로 완화, 서버 dedup/페이지네이션은 후속.
- **캐시 staleness** — mount 1회 fetch + 검색 후 refresh 만 → 다른 탭/사용자 기록은 실시간 미반영(의도적 단순화).
- **캐시 미스 재질의** — `size=20` 밖의 오래된 질의 클릭 시 결국 POST `/search`('복원' 강점이 부분적으로만 성립).
- **초기 1-RTT** — 첫 진입 시 `GET /history` 전까지 사이드바 비어 보일 수 있음(loading 처리).
- **effect/URL 동기화** — q 변경을 단일 source 로 강제하고 의존성(`[searchParams]`)+가드 설계 주의(중복/무한 루프 방지).
- **StrictMode 이중 effect(dev)** — mount fetch/검색 2회 호출 가능(멱등 무해, `ignore` 플래그로 setState 경합 방지).

## 미결 질문

- 사이드바 기록 노출 개수 N(예 8) 및 '더보기'/페이지네이션 필요 여부.
- 기록 항목 삭제/전체 지우기 UI 포함 여부(백엔드에 DELETE 기록 엔드포인트 없음 → 추가 시 백엔드 변경).
- 전역 기록 노출을 데모/내부용으로 허용할지, 사용자 스코프(백엔드 변경)를 후속 과제로 명시할지.
- 동일 query '항상 강제 재실행' 시맨틱 필요 여부(필요 시 `?q` 에 nonce 보강, 아니면 캐시복원-무해 전제 유지).
- 검색 버튼/Enter 의 `setSearchParams` 일원화 시 예시질문(추가/삭제·클릭=검색) 흐름과의 상호작용.
