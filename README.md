# 정책자금 지원 업무 플랫폼

정책공고(공고/규정) PDF를 구조화·RAG 최적화 청크로 변환하고, 그 데이터 위에서 자연어 검색·답변 합성, 공고 버전관리·diff, 질문 랭킹, 온보딩 가이드를 제공하는 내부 업무 플랫폼이다. **PDF 정책공고 → 구조화/RAG 청크(`chunks.xml` 정본 + `chunks.jsonl` 벡터 적재용) → 벡터/풀텍스트 검색 + 답변 합성**의 단방향 파이프라인을 중심으로, 공고 버전관리·랭킹·온보딩 기능이 함께 동작한다. 기본값은 **오프라인(OpenAI 키 불필요)** 으로, 결정론적 해시 임베딩 + 오프라인 답변 합성만으로 검색이 end-to-end 동작한다.

구성은 모노레포로, 4개 파트로 나뉜다: Python PDF→RAG 파이프라인([`pipeline/`](pipeline/)), Spring Boot 백엔드([`backend/`](backend/)), React+Vite 프론트엔드([`frontend/`](frontend/)), 그리고 Docker/nginx 배포 인프라.

## 디렉터리 구조

| 경로 | 역할 |
|------|------|
| [`pipeline/`](pipeline/) | PDF → RAG 청크 변환 파이프라인 (Python 3.10+, 오프라인 기본·결정론적) |
| [`backend/`](backend/) | Spring Boot 3.4.5 / Java 21 REST 백엔드 (검색·공고·랭킹·온보딩, 파이프라인을 동일 이미지에 번들) |
| [`frontend/`](frontend/) | React 18 + Vite 5 + TypeScript SPA |
| [`docs/`](docs/) | PRD·설계·OpenAPI 계약·사용자 플로우 문서 |
| [`source/`](source/) | 입력 정책공고 PDF (예: `1. 2026년 중소기업 정책자금 융자계획 변경공고(...)` 등 3종) |
| [`out/`](out/) | 파이프라인 산출물(`chunks.xml`/`chunks.jsonl`/`manifest.json`). git 추적 대상이며 백엔드가 부팅 시 읽기전용 마운트로 적재 |
| [`nginx/`](nginx/) | 엣지 리버스 프록시 설정([`nginx/nginx.conf`](nginx/nginx.conf)) |
| [`docker-compose.yml`](docker-compose.yml) | 4-서비스 전체 스택(mysql·backend·frontend·nginx) |

> `out/`에는 `source/`의 PDF 3종과 1:1로 매칭되는 정본 산출 폴더만 둔다. 같은 `chunk_id`(결정론적)는 `ChunkIngestService`가 PK upsert로 합치므로 동일 문서를 중복 폴더로 두면 부팅 시 재적재 작업만 늘 뿐 데이터는 중복되지 않는다 — 그래도 폴더는 source와 1:1로 유지하는 것을 권장한다.

## 빠른 시작 (Docker)

전체 스택은 `mysql`, `backend`(파이프라인 번들), `frontend`, `nginx` 4개 서비스로 구성된다. **호스트로 노출되는 포트는 엣지 nginx 뿐**이며, backend(8080)·frontend(80)는 nginx를 통해서만 접근한다.

```bash
# 1) .env 준비 (DB 자격증명, 선택적 OpenAI 키, nginx 포트)
cp .env.example .env   # 이후 DB_* / OPENAI_API_KEY / NGINX_PORT 편집

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
- OpenAI 키는 검색·동작상 선택이지만, **`.env`의 `OPENAI_API_KEY`는 비워 두면 안 된다.** 빈 값은 `application.yml`의 `${OPENAI_API_KEY:sk-noop}` 기본값을 덮어써 Spring AI 챗 모델 빈이 부팅에 실패하므로(검색은 오프라인이지만 Vision/분류 빈이 무조건 챗 모델을 끌어옴), 키가 없으면 `.env.example`처럼 **`OPENAI_API_KEY=sk-noop`** 센티넬을 둔다. 실제 OpenAI 기능을 쓸 때만 `sk-...` 키로 교체.

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
- OpenAI 키는 기본 동작(검색)에 불필요하다(`search.embedding.provider=hash`, `search.synth.provider=offline`, `search.retrieval=vector`). 다만 `OpenAiPageVisionExtractor`([소스](backend/src/main/java/com/policyfund/notices/preprocess/OpenAiPageVisionExtractor.java))가 무조건 등록되는 빈이라 **부팅 시 Spring AI 챗 모델이 필요**하다 — 따라서 `spring.ai.openai.api-key`는 최소한 센티넬 `sk-noop`이어야 하며(미설정 시 `application.yml` 기본값이 sk-noop), **빈 문자열이면 컨텍스트가 뜨지 않는다.** 실제 키가 필요한 경우는 OpenAI 임베딩/합성, PDF Vision OCR, 질문 분류기이며 — Vision OCR·질문 분류는 오프라인 폴백 빈이 없어 이미지 전용 PDF나 비캐시 랭킹 계산 시 sk-noop만으로는 그 호출이 실패한다.

**주요 엔드포인트** (베이스 `/api/v1`)

- 검색: `POST /search`(자연어 질의 → 후보 검색 + 답변 합성, 이력 저장) · `GET /search/history`(페이지네이션) · `GET·POST /search/examples`(예시 질문, 최대 5) · `DELETE /search/examples/{id}`
- 공고: `GET /notices/{category}`(category=`regulation`|`reference`, 버전 목록) · `POST /notices/{category}/revisions`(신규 버전 등록) · `GET /notices/{category}/versions/{version}/diff`(이전 버전 대비 블록 diff)
- PDF 전처리: `POST /notices/{category}/revisions/preprocess`(multipart PDF, 최대 50MB → ContentBlock[]) · `GET /notices/assets/{id}`(추출 페이지 PNG, sha256 64-hex)
- 랭킹/온보딩: `GET /rankings?period=...`(period 필수) · `GET /onboarding?period=...`(period 선택, 기본 `최근 30일`)
- 운영: `GET /actuator/health`(상태만 노출)

> 검색(기본 vector 경로): 질의를 256차원 해시 임베딩으로 변환 → `chunk_embedding` 전체 로드 후 in-app 코사인 유사도(brute-force, MySQL8 호환·VECTOR 타입 없음) top-20 → 오프라인 합성기가 최대 5건을 근거로 제시. 데이터는 부팅 시 [`out/`](out/)의 `chunks.jsonl`에서 적재된다.

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
| `OPENAI_API_KEY` | 백엔드·파이프라인 | Spring AI(gpt-4o·임베딩), Vision OCR, 질문 분류, 파이프라인 Vision에 사용. `sk-noop`(또는 미설정)이면 컨텍스트는 기동되고 실제 OpenAI 호출만 실패. **빈 문자열은 부팅 실패**(기본값 sk-noop을 덮어씀) | `sk-noop` |
| `DB_USERNAME` / `DB_PASSWORD` | 백엔드·MySQL | MySQL 자격증명. `local` 프로파일 코드 기본 `policyfund`/`policyfund`, `docker` 프로파일은 기본 없음 | `policyfund` (local) |
| `DB_ROOT_PASSWORD` | MySQL | MySQL root 비밀번호(헬스체크·초기화) | `change-me-root` (.env.example) |
| `SPRING_PROFILES_ACTIVE` | 백엔드 | datasource 바인딩 선택(`local`/`docker`). 미설정 시 datasource 없음 | (없음) |
| `NGINX_PORT` | 인프라 | 엣지 nginx 호스트 포트 | `80` |
| `search.retrieval` | 백엔드 | 검색 어댑터(`vector` 기본 / `fulltext`) | `vector` |
| `search.embedding.provider` | 백엔드 | 임베딩(`hash` 오프라인 기본 256차원 / `openai`) | `hash` |
| `search.synth.provider` | 백엔드 | 답변 합성(`offline` 기본 / `openai`) | `offline` |
| `search.ingest.on-startup` | 백엔드 | 부팅 시 `out/**/chunks.jsonl` 자동 적재(테이블 비었을 때) | `true` |
| `app.assets.dir` | 백엔드 | 추출 PNG 저장 디렉터리(`APP_ASSETS_DIR`로 오버라이드) | `./data/assets` |
| `VITE_API_BASE_URL` | 프론트엔드 | API 베이스 URL 오버라이드 | `/api/v1` |
| `PIPELINE_PYTHON` | Docker 런타임 | Spring ProcessBuilder가 호출할 파이프라인 venv 인터프리터 경로 | `/opt/pipeline-venv/bin/python` |
| `PYTHONUTF8` / `PYTHONIOENCODING` | Docker 런타임 | 한글 안전 처리를 위한 UTF-8 강제 | `1` / `utf-8` |

> `.env.example`은 `DB_PASSWORD=change-me`(루트 `DB_ROOT_PASSWORD=change-me-root`)를 배포하지만, 백엔드 `local` 프로파일(`application-local.yml`)의 **코드 기본값은 `policyfund`** 다 — `.env`를 쓰지 않고 `local` 프로파일로 직접 실행하면 `policyfund`가 적용된다. 두 출처의 기본값이 다른 점에 유의한다.

> `SOURCE_DATE_EPOCH`(파이프라인): `--generated-at` 미지정 시 `document/@generated_at` 산출에 사용(미설정 시 현재 UTC).

## 주요 기능

- **자연어 검색 + 답변 합성** — 정책공고 청크에 대한 RAG 검색. 기본은 MySQL 저장 임베딩 위 코사인 벡터 검색(오프라인 해시 임베딩 + 오프라인 합성), 선택적으로 MySQL FULLTEXT(ngram) 풀텍스트 검색 및 OpenAI 답변 합성(중복 요약·충돌 표기 포함)으로 전환 가능. 질의/답변은 검색 이력으로 저장된다.
- **공고 버전관리 / diff** — 공고(`regulation`)·참고자료(`reference`)를 단일 출처 문서로 버전 누적 관리하고, 직전 버전 대비 LCS 기반 블록 diff(same/add/del)를 제공한다.
- **질문 랭킹** — 검색 이력을 기간별로 분류·집계해 자주 묻는 질문 카테고리 랭킹을 산출하고 `ranking_cache`에 캐싱한다.
- **온보딩 가이드** — 랭킹 결과를 1:1로 학습 우선순위 리스트로 변환해 신규 담당자 온보딩에 활용한다.
- **PDF 전처리** — PDFBox로 페이지별 텍스트 레이어를 추출하고, 이미지 전용 페이지는 150-DPI PNG로 렌더링 후 Vision OCR로 텍스트화하여 `ContentBlock[]`을 생성한다.

## 문서

- 제품 요구사항: [`docs/prd/PRD.md`](docs/prd/PRD.md) · 백엔드 [`docs/prd/BACKEND_PRD.md`](docs/prd/BACKEND_PRD.md) · 보충 [`docs/prd/BACKEND_PRD_SUPPLEMENT.md`](docs/prd/BACKEND_PRD_SUPPLEMENT.md) · 구현 계획 [`docs/prd/IMPLEMENTATION_PLAN.md`](docs/prd/IMPLEMENTATION_PLAN.md)
- 파이프라인 설계: 개요 [`docs/prd/pdf-to-xml-pipeline.md`](docs/prd/pdf-to-xml-pipeline.md) — 단계별 세부 [`00-foundation`](docs/prd/pdf-to-xml-pipeline/00-foundation.md) · [`01-extraction`](docs/prd/pdf-to-xml-pipeline/01-extraction.md) · [`02-structure-recognition`](docs/prd/pdf-to-xml-pipeline/02-structure-recognition.md) · [`03-table-processing`](docs/prd/pdf-to-xml-pipeline/03-table-processing.md) · [`04-nontext-and-providers`](docs/prd/pdf-to-xml-pipeline/04-nontext-and-providers.md) · [`05-chunking`](docs/prd/pdf-to-xml-pipeline/05-chunking.md) · [`06-relations`](docs/prd/pdf-to-xml-pipeline/06-relations.md) · [`07-spring-integration`](docs/prd/pdf-to-xml-pipeline/07-spring-integration.md)
- API 계약: [`docs/api/openapi.yaml`](docs/api/openapi.yaml) (OpenAPI 3.1, `/api/v1`, 11개 오퍼레이션 / 경로 10개)
- 사용자 플로우: 프론트 [`docs/user_flow/user_flow.md`](docs/user_flow/user_flow.md) · 백엔드 [`docs/user_flow/backend_user_flow.md`](docs/user_flow/backend_user_flow.md)
- 단계별 구현 계획: [`docs/superpowers/plans/`](docs/superpowers/plans/) (P1 파운데이션 ~ P4 랭킹/온보딩)

> 참고: 일부 설계 문서는 Java 25 / 패키지 `kr.co.hakjisa.policyfund`를 언급하나, 실제 코드는 **Java 21 / 패키지 `com.policyfund`** 가 기준이다.
