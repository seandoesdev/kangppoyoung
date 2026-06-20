# P1 세부 구현 계획 — 다문서 커버리지 보장

> 상위 문서: [`plan_overview.md`](plan_overview.md) P1. 본 설계 승인 후 구현한다.
> 기준선: [`../eval/results-2026-06-20-baseline.md`](../eval/results-2026-06-20-baseline.md)
> (평균 53.8/100, **2출처 실제 조합 1/10**).

## 1. 목표 · 성공 기준

- **목표**: 답이 2개 이상 문서를 합쳐야 완성되는 질의에서, 검색 후보가 여러 문서에 걸치도록 보장한다.
- **성공 기준**(eval 세트 재채점):
  - 2출처 실제 조합 **1/10 → ≥ 5/10**.
  - 다문서형 항목(2·4·6·9번) 점수 상승, 평균 점수 상승.
  - 단일문서형(1·5·10)·반대 케이스(온라인 신청 시스템) **무회귀**(타 문서 노이즈로 품질 저하 없음).

## 2. 현재 구조 · 근본 원인

- `VectorRetrievalAdapter`: 코사인 상위 TOP_K(40, 섹션캡 6) → seq 이웃 확장(±6) → 최종 섹션캡(18)·총 90.
- 섹션캡은 **(문서 + article_no)** 단위라 *한 문서 내* 쏠림만 막는다.
- 코퍼스 3문서 중 **doc1(변경공고, 1014청크)**이 양적으로 우세 → doc2(참고자료)·doc3(기초가이드)의
  관련 청크가 top-K 밖으로 밀려, 후보가 사실상 단일 문서가 된다. (eval 1·2·4·9번에서 단일 출처로 관측됨)

## 3. 설계

### 변경 1 (핵심) — 문서 균형 히트 선정 (`VectorRetrievalAdapter`)

코사인 정렬 후 히트를 고를 때, **관련도 게이트를 통과한 각 문서에 최소 쿼터를 먼저 배정**한 뒤
나머지를 전역 점수로 채운다. 관련 없는 문서는 게이트에서 막혀 강제로 끌려오지 않는다.

절차:
1. `ranked` = 전체 청크 cosine 내림차순. `top = ranked[0].score`.
2. **Phase 1 (문서 쿼터)**: 각 `document_id`에 대해, 그 문서 상위 청크 중
   `score ≥ top * RELEVANCE_RATIO` 인 것을 섹션캡(6) 지키며 `MIN_PER_DOC`개까지 hits에 우선 배정.
3. **Phase 2 (전역 채움)**: 남은 자리를 `ranked` 순서로 섹션캡 지키며 `TOP_K`까지 채움.
4. 이후 기존 seq 이웃 확장(±6) + 최종 섹션캡(18)·총 90 유지.

의사코드:
```text
float top = ranked.get(0).score();
double floor = top * RELEVANCE_RATIO;            // 상대 게이트 (예: 0.70)
LinkedHashSet<String> hitIds; Map<String,Integer> perDoc, perSection;

// Phase 1: 문서별 최소 쿼터 (관련도 게이트)
for (String doc : distinctDocsInRankOrder) {
  int taken = 0;
  for (Scored s : rankedOf(doc)) {                // 해당 문서 청크를 점수순으로
    if (taken >= MIN_PER_DOC) break;
    if (s.score() < floor) break;                 // 관련도 미달이면 이 문서 쿼터 중단
    if (sectionCount(perSection, s) >= MAX_PER_SECTION) continue;
    add(hitIds, perDoc, perSection, s); taken++;
  }
}
// Phase 2: 전역 점수로 TOP_K 까지 채움
for (Scored s : ranked) {
  if (hitIds.size() >= TOP_K) break;
  if (hitIds.contains(s.id())) continue;
  if (sectionCount(perSection, s) >= MAX_PER_SECTION) continue;
  add(...);
}
```

파라미터(초기값, eval로 튜닝):

| 파라미터 | 초기값 | 의미 |
|---|---|---|
| `MIN_PER_DOC` | 4 | 관련도 통과 문서당 최소 히트 수 |
| `RELEVANCE_RATIO` | 0.70 | 상대 게이트(top 대비). 미달 청크는 쿼터에서 제외. doc2/3가 점수보다 물량에 밀리는 관측을 반영해 관대하게 시작, eval로 튜닝 |
| `TOP_K` | 40 | 전체 히트 수(기존) |
| `MAX_PER_SECTION` | 6 | 섹션당 히트 캡(기존) |

> 게이트는 코사인 분포에 민감하므로 **상대 게이트(top·ratio)** 를 기본으로 하되, 절대 floor(예: 0.35)도
> 비교 측정한다. `MIN_PER_DOC`이 너무 크면 단일문서 질의에 노이즈가 늘어난다.

### 변경 2 — refiner 교차문서 점검 (`OpenAiRetrievalRefiner`)

- 후보 다이제스트에 **문서명(`fileName`)** 을 포함해 refiner가 문서 분포를 보게 한다.
- 시스템 프롬프트 보강: "질의의 일부가 현재 후보에 없는 **다른 문서**의 정보를 요구하면 `needsMore=true`,
  `followUpQuery`에 그 측면을 겨냥한 키워드"를 명시. (변경 1로 1차에서 이미 다문서면 refiner는 '충분'.)
- 게이트: P1에서는 절차/목록 외에 **복합 요구 질의**도 점검하도록 약간 넓히고, 정식 확대는 P2에서.

### 변경 3 (선택) — 병합 시 문서 보장 (`CandidateMerge` / `SearchService`)

- hop-1 ∪ hop-2 병합 시 섹션캡과 별개로 **문서당 최소 보장**을 둔다. 변경 1+2로 충분하면 생략.

## 4. 리스크 · 완화

| 리스크 | 완화 |
|---|---|
| 단일문서 질의에 타 문서 노이즈 유입 | 관련도 게이트(`RELEVANCE_RATIO`) — 미달 문서는 쿼터 미배정 |
| 게이트 임계 민감 | eval로 튜닝(상대/절대 비교), `MIN_PER_DOC` 보수적 |
| 후보 수 증가로 합성 비용·지연↑ | 총 캡 90 유지, `MIN_PER_DOC` 작게(4) |
| refiner 게이트 확대로 LLM 호출↑ | P1은 최소 확대, 비용 큰 정식 확대는 P2 |

## 5. 테스트

- **단위**(`VectorRetrievalAdapterTest`):
  - 문서 균형: doc1 다수 + doc2 소수(관련) → 후보에 doc2 포함됨(쿼터). 게이트 미달 doc3 → 미포함.
  - 게이트 경계: 상대 floor 근처 청크의 포함/제외 동작.
- **통합/평가**: `docs/eval/search-eval.md` 재채점 → 2출처 조합률·항목 점수를 베이스라인과 비교.

## 6. 변경 파일 · 운영

- `VectorRetrievalAdapter.java` (문서 균형 선정), `OpenAiRetrievalRefiner.java` (다이제스트 문서명 + 프롬프트),
  (선택) `CandidateMerge.java` / `SearchService.java`.
- 테스트: `VectorRetrievalAdapterTest.java` (+케이스).
- **재적재 불필요**(스키마·임베딩 불변). **롤백**: `MIN_PER_DOC=0`(또는 `RELEVANCE_RATIO` 매우 크게)으로
  Phase 1을 비활성화하면 기존 동작과 동일.

## 7. 진행 단계

1. **Phase 1**: 변경 1(문서 균형 retrieval) 구현 → eval 재채점으로 효과·파라미터 측정.
2. 부족하면 **변경 2**(refiner 교차문서) 추가 → 재측정.
3. 그래도 부족하면 **변경 3**.

## 8. 검증 기준

구현 후 `docs/eval/search-eval.md`로 재채점하고, 결과를 `docs/eval/results-<날짜>.md` 신규 베이스라인으로
저장해 2026-06-20 베이스라인 대비 **2출처 조합률 · 평균 점수 · 항목별 판정**을 비교한다.
