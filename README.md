# 정책자금 지원 업무 플랫폼

정책공고(공고/규정) PDF를 구조화·RAG 최적화 청크로 변환하고, 그 데이터 위에서 자연어 검색·답변 합성, 공고 버전관리·diff, 질문 랭킹, 온보딩 가이드를 제공하는 내부 업무 플랫폼이다. **PDF 정책공고 → 구조화/RAG 청크(`chunks.xml` 정본 + `chunks.jsonl` 벡터 적재용) → 벡터/풀텍스트 검색 + 답변 합성**의 단방향 파이프라인을 중심으로, 공고 버전관리·랭킹·온보딩 기능이 함께 동작한다. 검색 기본값은 **OpenAI 모드**로, 의미 임베딩(1536차원) + LLM(gpt-4o) 답변 합성으로 동작하며 실제 `OPENAI_API_KEY`가 필요하다(키 없이 오프라인 해시 임베딩 + 근거 나열 모드로 전환도 가능). PDF→RAG 파이프라인 자체는 키 없이 오프라인으로 동작한다.

구성은 모노레포로, 4개 파트로 나뉜다: Python PDF→RAG 파이프라인([`pipeline/`](pipeline/)), Spring Boot 백엔드([`backend/`](backend/)), React+Vite 프론트엔드([`frontend/`](frontend/)), 그리고 Docker/nginx 배포 인프라.

## 디렉터리 구조

| 경로 | 역할 |
|------|------|
| [`pipeline/`](pipeline/) | PDF → RAG 청크 변환 파이프라인 (Python 3.10+, 오프라인 기본·결정론적) |
| [`backend/`](backend/) | Spring Boot 3.4.5 / Java 21 REST 백엔드 (검색·공고·랭킹·온보딩, 파이프라인을 동일 이미지에 번들) |
| [`frontend/`](frontend/) | React 18 + Vite 5 + TypeScript SPA |
| [`docs/`](docs/) | OpenAPI 계약(`api/`)·사용자 플로우(`user_flow/`)·검색 평가(`eval/`)·구현 계획(`plan/`)·통합 PRD(`prd/`) |
| [`source/`](source/) | 입력 정책공고 PDF (예: `1. 2026년 중소기업 정책자금 융자계획 변경공고(...)` 등 3종) |
| [`out/`](out/) | 파이프라인 산출물(`chunks.xml`/`chunks.jsonl`/`manifest.json`). git 추적 대상이며 백엔드가 부팅 시 읽기전용 마운트로 적재 |
| [`nginx/`](nginx/) | 엣지 리버스 프록시 설정([`nginx/nginx.conf`](nginx/nginx.conf)) |
| [`docker-compose.yml`](docker-compose.yml) | 4-서비스 전체 스택(mysql·backend·frontend·nginx) |

> `out/`에는 `source/`의 PDF 3종과 1:1로 매칭되는 정본 산출 폴더만 둔다. 같은 `chunk_id`(결정론적)는 `ChunkIngestService`가 PK upsert로 합치므로 동일 문서를 중복 폴더로 두면 부팅 시 재적재 작업만 늘 뿐 데이터는 중복되지 않는다 — 그래도 폴더는 source와 1:1로 유지하는 것을 권장한다.

## 빠른 시작 (Docker)

전체 스택은 `mysql`, `backend`(파이프라인 번들), `frontend`, `nginx` 4개 서비스로 구성된다. **호스트로 노출되는 포트는 엣지 nginx 뿐**이며, backend(8080)·frontend(80)는 nginx를 통해서만 접근한다.

```bash
# 1) .env 준비 (DB 자격증명, OpenAI 키[기본 검색에 필수], nginx 포트)
cp .env.example .env   # 이후 DB_* / OPENAI_API_KEY(실제 sk- 키) / NGINX_PORT 편집

# 2) 전체 스택 빌드·기동
docker compose up --build

# 호스트 80 포트가 사용 중이면 NGINX_PORT 로 오버라이드
NGINX_PORT=8088 docker compose up --build
```

기동 후 헬스 체크(엣지 nginx → backend):

```bash
curl http://localhost:${NGINX_PORT:-80}/actuator/health
```

- 앱 진입: `http://localhost:${NGINX_PORT:-80}/` (프론트엔드 SPA)
- API: `http://localhost:${NGINX_PORT:-80}/api/v1/...`
- 백엔드는 부팅 시 [`out/`](out/)의 `**/chunks.jsonl`을 비어있는 `chunk_embedding` 테이블에 자동 적재한다(`./out:/app/out:ro` 마운트). 검색 데이터를 채우려면 먼저 파이프라인으로 `out/`을 생성해 두면 된다.
- **검색 기본값이 OpenAI 모드(임베딩 + gpt-4o 답변 합성)이므로 실제 `OPENAI_API_KEY`가 필요하다.** 질의 임베딩·답변 합성·부팅 시 청크 임베딩 적재가 모두 OpenAI를 호출한다. `sk-noop`이면 컨텍스트는 뜨지만 검색·부팅 적재가 실패하고, **빈 문자열이면 부팅 자체가 실패**한다(Vision/분류 빈이 무조건 챗 모델을 끌어옴). 키 없이 돌리려면 `.env.example` 주석대로 `SEARCH_EMBEDDING_PROVIDER=hash`·`SEARCH_SYNTH_PROVIDER=offline`로 전환하고 `OPENAI_API_KEY=sk-noop`을 둔다.

## 사용 방법

### 1. PDF → RAG 파이프라인 ([`pipeline/`](pipeline/))

PDF를 검색·추론에 최적화된 `<chunk>`(= `<meta>` 구조/출처/관계 + `<content>` 의미) 기반 문서로 변환한다. 산출은 결정론적이며 외부 호출 없이 오프라인으로 동작한다.

```bash
# 설치 (Python 3.10+, 하드 의존성 pdfplumber/pydantic/lxml)
python -m pip install -r pipeline/requirements.txt

# 실행: source/ 의 PDF를 변환 → out/ 에 산출 (모듈 진입점 python -m pipeline)
python -m pipeline --input "source/문서.pdf" --outdir "out/문서"

# 바이트 동일 재현(골든 회귀): 타임스탬프 고정
python -m pipeline --input "source/문서.pdf" --outdir "out/문서" --generated-at 2026-01-01T00:00:00+00:00
```

주요 CLI 플래그(전체는 [`pipeline/cli.py`](pipeline/cli.py)의 argparse가 기준):

| 플래그 | 설명 | 기본값 |
|--------|------|--------|
| `--input` | 입력 PDF 경로 (필수) | — |
| `--outdir` | 산출 디렉터리 (필수) | — |
| `--doc-id` | 문서 ID | PDF 내용 해시 |
| `--offline` | 오프라인 모드(항상 True, CLI에서 끌 수 없음) | True |
| `--confidence-threshold` | 일반 청크 신뢰도 임계 | 0.7 |
| `--table-confidence-threshold` | 표 청크 신뢰도 임계 | 0.6 |
| `--max-chunk-chars` | 청크 최대 문자 수 | 800 |
| `--max-input-mb` | 입력 PDF 최대 크기(MB) | 100 |
| `--max-pages` | 최대 페이지 수 | 300 |
| `--generated-at` | ISO-8601 타임스탬프(바이트 동일 산출용) | 현재 UTC |
| `--no-verify` | 자체 검증 생략 | off |

**산출물**(`<outdir>/`):

- `chunks.xml` — 원본 구조 정본 XML (`<document>` + `<chunk>` 요소)
- `chunks.jsonl` — 벡터DB 적재용(한 줄당 한 청크: `chunk_id`, `document_id`, `content_type`, `embedding_text`, `metadata`; 임베딩 빈 청크는 제외)
- `manifest.json` — 상태·집계(청크/타입별/페이지/스캔페이지)·추출방식·검토필요(review_required)·타이밍·검증 리포트
- stdout 마지막 줄 — Spring이 파싱하는 단일 JSON 센티넬 `{"@@MANIFEST@@":true, ...}`

**자체 검증**(`--no-verify` 미지정 시 자동, [`pipeline/verify.py`](pipeline/verify.py)): 문자 보존율(text_coverage, 게이트 ≥0.99) · `chunk_id` 유일성 · XML↔JSONL 정합 · XML round-trip 텍스트 동등성 · 관계 무결성(dangling 없음). `xml_roundtrip`/`xml_jsonl_parity` 실패만 종료코드 4를 강제하고, 보존율 게이트 미달은 기록만 한다.

**종료 코드**: `0` 성공(부분 포함) · `2` 인자 오류 · `3` 입력 오류(파일 없음/크기 초과) · `4` 검증 실패 · `5` 한계 초과(페이지 수) · `1` 내부 오류.

테스트:

```bash
# 전체 (pytest.ini: testpaths=tests, pythonpath=.)
pytest

# 단위 테스트만 (라이브 스택/소스 PDF 의존 테스트 제외, 미존재 시 자동 skip)
pytest tests/test_ids.py tests/test_model_schema.py tests/test_relations.py tests/test_tables.py tests/test_table_crosspage.py tests/test_xml_roundtrip.py tests/test_providers.py
```

> 참고: 오프라인 기본에서 이미지는 신뢰도 0.3의 `infographic` 청크로 `needs_review(offline_fallback)` 플래그가 붙고, born-digital 텍스트 레이어는 약 100% 보존된다. OpenAI Vision/OCR(tesseract) 경로는 선택이며 기본 동작에 불필요하다. 세부 옵션은 [`pipeline/README.md`](pipeline/README.md) 참조.

### 2. 백엔드 ([`backend/`](backend/), Spring Boot)

```bash
# 로컬 MySQL(localhost:3306/policyfund) 대상으로 실행 — local 프로파일 필수
cd backend && SPRING_PROFILES_ACTIVE=local ./gradlew bootRun

# 부트 가능한 jar 빌드 (테스트 생략)
cd backend && ./gradlew clean bootJar --no-daemon -x test          # Linux/CI
cd backend; .\gradlew.bat clean bootJar -x test                    # Windows

# 빌드된 jar 실행 (프로파일 + 선택적 OpenAI 키)
SPRING_PROFILES_ACTIVE=local OPENAI_API_KEY=sk-... java -jar backend/build/libs/policyfund-backend-0.1.0.jar

# 전체 테스트 (Docker 필요 — Testcontainers MySQL 8.0)
cd backend && ./gradlew test
```

**필요한 서비스/프로파일**

- MySQL 8.0이 필요하다. 베이스 `application.yml`에는 datasource가 없으므로 반드시 `SPRING_PROFILES_ACTIVE=local`(localhost:3306) 또는 `docker`(host `mysql`)를 활성화해야 한다. `docker` 프로파일은 `DB_USERNAME`/`DB_PASSWORD`에 기본값이 없어 env로 주입해야 한다.
- 스키마는 Flyway(`V1`~`V3`)가 소유한다(`ddl-auto=validate`).
- **검색 기본값이 OpenAI(`search.embedding.provider=openai`, `search.synth.provider=openai`, `search.retrieval=vector`)이므로 실제 `OPENAI_API_KEY`가 필요하다** — 질의 임베딩·gpt-4o 답변 합성·부팅 시 청크 임베딩 적재가 모두 OpenAI를 호출한다. 추가로 `OpenAiPageVisionExtractor`([소스](backend/src/main/java/com/policyfund/notices/preprocess/OpenAiPageVisionExtractor.java))·질문 분류기도 오프라인 폴백 빈이 없어 OpenAI를 쓴다. `sk-noop`이면 컨텍스트만 뜨고 실제 호출은 실패하며, **빈 문자열이면 컨텍스트가 뜨지 않는다.** 키 없이 돌리려면 provider를 `hash`/`offline`로 전환한다(이 경우 검색은 동작하지만 의미 검색 품질이 낮고 답변은 근거 나열에 그치며, Vision OCR·비캐시 랭킹은 여전히 실패).

**주요 엔드포인트** (베이스 `/api/v1`)

- 검색: `POST /search`(자연어 질의 → 후보 검색 + 답변 합성, 이력 저장) · `GET /search/history`(페이지네이션) · `GET·POST /search/examples`(예시 질문, 최대 5) · `DELETE /search/examples/{id}`
- 공고: `GET /notices/{category}`(category=`regulation`|`reference`, 버전 목록) · `POST /notices/{category}/revisions`(신규 버전 등록) · `GET /notices/{category}/versions/{version}/diff`(이전 버전 대비 블록 diff)
- PDF 전처리: `POST /notices/{category}/revisions/preprocess`(multipart PDF, 최대 50MB → ContentBlock[]) · `GET /notices/assets/{id}`(추출 페이지 PNG, sha256 64-hex)
- 랭킹/온보딩: `GET /rankings?period=...`(period 필수) · `GET /onboarding?period=...`(period 선택, 기본 `최근 30일`)
- 운영: `GET /actuator/health`(상태만 노출)

> 검색(기본 vector 경로): 질의를 OpenAI 임베딩(1536차원)으로 변환 → `chunk_embedding` 전체 로드 후 in-app 코사인 유사도(brute-force, MySQL8 호환·VECTOR 타입 없음) top-20 → gpt-4o 합성기가 답변을 생성(근거 조항은 LLM 출력이 아니라 실제 검색 상위 5건으로 확정 채움, 중복 요약·상충 표기 포함). 데이터는 부팅 시 [`out/`](out/)의 `chunks.jsonl`에서 OpenAI 임베딩으로 적재된다.

### 3. 프론트엔드 ([`frontend/`](frontend/), React + Vite)

```bash
cd frontend
npm install
npm run dev        # Vite 개발 서버 (/api/v1 → http://localhost:8080 프록시)
npm run build      # tsc -b 타입체크 후 vite 프로덕션 빌드
npm run preview    # 프로덕션 빌드 로컬 미리보기
```

**API 베이스 URL 설정**: [`src/api/client.ts`](frontend/src/api/client.ts)에서 `import.meta.env.VITE_API_BASE_URL ?? '/api/v1'`로 읽는다. 미설정 시 상대경로 `/api/v1`을 사용하며, 개발 서버에서는 Vite 프록시가 이를 `http://localhost:8080`(Spring)로 전달한다. 프로덕션에서는 nginx가 프록시한다.

라우팅 페이지: 통합 검색(`/`) · 정책 자금 공고(`/notice/:category`, `regulation`=공고 / `reference`=참고자료) · 질문 분석(`/ranking`) · 온보딩 가이드(`/onboarding`).

> 현재 Search 페이지만 라이브 백엔드(`searchPolicy`)에 연결되어 있고, Ranking·Onboarding·PolicyNotice는 아직 [`src/data/mock.ts`](frontend/src/data/mock.ts)의 목 데이터를 사용한다.

## 환경 변수

| 변수 | 적용 대상 | 설명 | 기본/오프라인값 |
|------|-----------|------|------------------|
| `OPENAI_API_KEY` | 백엔드·파이프라인 | Spring AI(gpt-4o·임베딩), Vision OCR, 질문 분류에 사용. **기본 검색이 openai라 실제 키 필요.** `sk-noop`이면 기동만 가능(검색·적재 실패), **빈 문자열은 부팅 실패** | 실제 `sk-...` 키 |
| `DB_USERNAME` / `DB_PASSWORD` | 백엔드·MySQL | MySQL 자격증명. `local` 프로파일 코드 기본 `policyfund`/`policyfund`, `docker` 프로파일은 기본 없음 | `policyfund` (local) |
| `DB_ROOT_PASSWORD` | MySQL | MySQL root 비밀번호(헬스체크·초기화) | `change-me-root` (.env.example) |
| `SPRING_PROFILES_ACTIVE` | 백엔드 | datasource 바인딩 선택(`local`/`docker`). 미설정 시 datasource 없음 | (없음) |
| `NGINX_PORT` | 인프라 | 엣지 nginx 호스트 포트 | `80` |
| `search.retrieval` | 백엔드 | 검색 어댑터(`vector` 기본 / `fulltext`) | `vector` |
| `search.embedding.provider` | 백엔드 | 임베딩(`openai` 기본 1536차원 / `hash` 오프라인 256차원). `SEARCH_EMBEDDING_PROVIDER`로 오버라이드 | `openai` |
| `search.synth.provider` | 백엔드 | 답변 합성(`openai` 기본 gpt-4o / `offline` 근거 나열). `SEARCH_SYNTH_PROVIDER`로 오버라이드 | `openai` |
| `search.ingest.on-startup` | 백엔드 | 부팅 시 `out/**/chunks.jsonl` 자동 적재(테이블 비었을 때) | `true` |
| `app.assets.dir` | 백엔드 | 추출 PNG 저장 디렉터리(`APP_ASSETS_DIR`로 오버라이드) | `./data/assets` |
| `VITE_API_BASE_URL` | 프론트엔드 | API 베이스 URL 오버라이드 | `/api/v1` |
| `PIPELINE_PYTHON` | Docker 런타임 | Spring ProcessBuilder가 호출할 파이프라인 venv 인터프리터 경로 | `/opt/pipeline-venv/bin/python` |
| `PYTHONUTF8` / `PYTHONIOENCODING` | Docker 런타임 | 한글 안전 처리를 위한 UTF-8 강제 | `1` / `utf-8` |

> `.env.example`은 `DB_PASSWORD=change-me`(루트 `DB_ROOT_PASSWORD=change-me-root`)를 배포하지만, 백엔드 `local` 프로파일(`application-local.yml`)의 **코드 기본값은 `policyfund`** 다 — `.env`를 쓰지 않고 `local` 프로파일로 직접 실행하면 `policyfund`가 적용된다. 두 출처의 기본값이 다른 점에 유의한다.

> `SOURCE_DATE_EPOCH`(파이프라인): `--generated-at` 미지정 시 `document/@generated_at` 산출에 사용(미설정 시 현재 UTC).

## 주요 기능

- **자연어 검색 + 답변 합성** — 정책공고 청크에 대한 RAG 검색. 기본은 OpenAI 의미 임베딩(1536차원) 위 코사인 벡터 검색 + gpt-4o 답변 합성(근거 조항은 실제 검색 상위 5건으로 확정 채움, 중복 요약·상충 표기 포함). 키 없이 돌릴 땐 오프라인 해시 임베딩 + 근거 나열 합성으로, 또는 MySQL FULLTEXT(ngram) 풀텍스트 검색으로 전환 가능. 질의/답변은 검색 이력으로 저장된다.
- **공고 버전관리 / diff** — 공고(`regulation`)·참고자료(`reference`)를 단일 출처 문서로 버전 누적 관리하고, 직전 버전 대비 LCS 기반 블록 diff(same/add/del)를 제공한다.
- **질문 랭킹** — 검색 이력을 기간별로 분류·집계해 자주 묻는 질문 카테고리 랭킹을 산출하고 `ranking_cache`에 캐싱한다.
- **온보딩 가이드** — 랭킹 결과를 1:1로 학습 우선순위 리스트로 변환해 신규 담당자 온보딩에 활용한다.
- **PDF 전처리** — PDFBox로 페이지별 텍스트 레이어를 추출하고, 이미지 전용 페이지는 150-DPI PNG로 렌더링 후 Vision OCR로 텍스트화하여 `ContentBlock[]`을 생성한다.

## 문서

- API 계약: [`docs/api/openapi.yaml`](docs/api/openapi.yaml) (OpenAPI 3.1, `/api/v1`, 11개 오퍼레이션 / 경로 10개)
- 사용자 플로우: [`docs/user_flow/user_flow.md`](docs/user_flow/user_flow.md) — 제품(프론트)+백엔드 처리 흐름을 합친 **단일 정본**(UC별 화면·백엔드·핵심규칙)
- 검색 평가: 세트 [`docs/eval/search-eval.md`](docs/eval/search-eval.md) · 결과 베이스라인 [`docs/eval/results-2026-06-20-baseline.md`](docs/eval/results-2026-06-20-baseline.md)
- 향후 구현 계획: [`docs/plan/search-history-sidebar-plan.md`](docs/plan/search-history-sidebar-plan.md) (검색 기록 좌측 사이드바 노출)
- 제품·기술 요구사항(PRD): [`docs/prd/PRD.md`](docs/prd/PRD.md) — 제품·백엔드·파이프라인을 통합한 **단일 정본**(UC·FR·데이터모델·API계약·파이프라인 계약·NFR·로드맵). 기준선은 [`docs/user_flow/user_flow.md`](docs/user_flow/user_flow.md)

> 참고: 일부 설계 문서는 Java 25 / 패키지 `kr.co.hakjisa.policyfund`를 언급하나, 실제 코드는 **Java 21 / 패키지 `com.policyfund`** 가 기준이다.
