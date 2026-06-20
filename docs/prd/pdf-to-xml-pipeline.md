# PDF → RAG Chunk 변환 파이프라인 설계 — 정책자금 지원 업무 플랫폼 (개요)

> 제품 요구사항 문서(Product Requirements Document) / 설계 문서 · 얼개 + 문서 맵
> 관련 문서: [PRD](./PRD.md) · 세부: [pdf-to-xml-pipeline/](./pdf-to-xml-pipeline/)
> 버전: v0.2 (구현용 분할) · 최종 수정: 2026-06-17

---

## 1. 개요 (Overview)

본 문서는 정책자금 규정·지침·절차 PDF를 **RAG(Retrieval-Augmented Generation)에 최적화된
Chunk 기반 구조화 문서**로 변환하는 **독립 Python 파이프라인**의 설계와, 이를 호출하는
**Spring ↔ Python 계약**을 정의한다.

목표는 단순 텍스트 추출이 아니다. 사람이 규정 문서를 읽을 때 자연스럽게 이해하는
**위계(편-장-절-조-항-호-목)·의미·관계**를 보존하면서, 검색과 추론에 곧바로 쓸 수 있는
**`<chunk>` 단위 구조**로 변환하는 것이 핵심이다. 모든 데이터는 `<chunk>`로 쪼개지고, 각
`<chunk>`는 구조·출처·관계를 담는 `<meta>`와 의미만 담는 `<content>`로 분리된다.

```
<chunk id="..."><meta>...</meta><content>...</content></chunk>
```

파이프라인은 동일 입력에서 **두 산출물을 분리 생성**한다.

- **원본 구조 보존 XML**(`chunks.xml`): 사람이 읽는 정본. 한 `<chunk>` 단위로 meta+content가
  자기완결적이라 검색 결과 하나로 원문 위치·문맥을 복원한다.
- **Vector DB 적재 JSONL**(`chunks.jsonl`): 한 줄 = 한 청크 = `{chunk_id, content_type,
  embedding_text, metadata}` 최소 스키마. 임베딩·검색 전용.

이 파이프라인은 나중에 Spring 백엔드가 `ProcessBuilder`로 **스크립트 실행**해 호출한다. 본
설계는 그 실행 계약(CLI 인자·stdout JSON·종료코드·자산 sha256 규약)을 명문화한다. Java 내부
구현은 사용자가 본 계약에 맞춰 별도 수정한다(본 문서는 Java 코드를 정의하지 않는다).

> 본 문서의 도메인 원칙은 [PRD](./PRD.md)를 계승한다. **근거 없는 답 금지**, **출처 항상
> 명시**, **단일 진실 문서**, **승인 게이트(전처리는 등록을 확정하지 않음)** 원칙이 청크의
> 출처·신뢰도·`review_required` 신호에 그대로 적용된다.

---

## 2. 목표 및 비목표 (Goals & Non-Goals)

### 2.1 목표 (Goals)

- 업로드 PDF를 **모든 데이터가 `<chunk>`**(meta+content)로 분할된 구조화 문서로 변환한다.
  meta=구조·출처·관계, content=의미(답변 근거)만 담는다.
- 표는 표 전체가 아니라 **각 Row를 독립 Chunk**로 정규화하고, 컬럼을 `<col name="컬럼명">값`
  형식으로 보존하며, 병합셀 반복 채움·다단헤더 결합·분할표 논리 병합·섹션 상속을 적용하고,
  Record마다 검색용 `<embedding_text>`를 생성한다.
- 인포그래픽·스크린샷·순서도 등 비텍스트 요소는 **OCR 평문 저장이 아니라 의미를 자연어로
  설명**하고, 순서도/관계도는 관계를 보존(Mermaid)한다.
- 텍스트 레이어 추출을 1순위로 하고, **문서 전체를 무조건 이미지로 변환하지 않으며**, 스캔본·
  깨짐·표 붕괴·도식 영역에만 OCR/layout_analysis를 한정 적용한다. 추출 방식은
  `extract_method`(pdf_text|ocr|layout_analysis)로 청크마다 기록한다.
- 관계(parent·previous·next·related·heading_path)를 meta에 저장해 **검색 결과 하나로 원문
  위치·문맥을 복원**할 수 있게 한다.
- **원본 복원용 XML과 검색용 JSONL을 분리** 산출하고, 동일 chunk_id로 1:1 교차 복원한다.
- 동일 입력(동일 PDF 바이트 + 동일 파이프라인 버전 + 동일 구성 + **동일 실행 환경**) → **동일
  출력**(결정성·멱등). LLM/Vision 개입 청크만 비결정으로 분리하고 캐싱·`review_required`로
  가드한다.

### 2.2 비목표 (Non-Goals)

- **Spring/Java 내부 구현을 정의하지 않는다.** 본 문서는 파이프라인 설계와 Spring↔Python
  계약만 정의한다. Java 측 코드(컨트롤러·서비스·예외 매핑)는 사용자가 본 계약에 맞춰 수정한다.
- **임베딩 벡터 생성·Vector DB 적재 동작 자체는 범위 밖**이다. 파이프라인은 적재 가능한
  `chunks.jsonl`까지만 산출한다(임베딩 모델 호출·upsert는 Spring/적재 워커 책임).
- **자동 승인 금지**: `review_required`는 비차단 신호일 뿐 등록을 확정하지 않는다.
- **법령 표준(Akoma Ntoso 등) 풀 준수 금지**: 외부 상호운용 요구가 없으므로 과잉이다.
- **OCR/LLM 산출의 무검증 정본 채택 금지**: 검증·신뢰도 게이트를 통과하기 전까지 저신뢰로
  표시한다.
- **2차(stored) 프롬프트 인젝션의 소비측 방어는 범위 밖**이다. 다만 본 파이프라인 산출
  `embedding_text`가 RAG 답변에 재주입될 수 있으므로, **외부 데이터에서 유도된 청크는 메타에
  마킹**해 소비측이 신뢰 경계를 적용할 수 있게 신호만 제공한다(§21).

---

## 3. 핵심 원칙 (Core Principles)

| 원칙 | 의미 |
| --- | --- |
| 모든 데이터는 Chunk | 문단·목록·표 Row·표 주석·그림 설명·절차 단계·순서도 노드/관계·스크린샷·경고·각주·참조까지 전부 `<chunk>`로 분할한다. |
| Meta / Content 분리 | 구조·출처·관계 = `<meta>`, 의미 = `<content>`. content에는 page_no·bbox·chunk_id 등 메타를 절대 넣지 않는다. |
| 답변 근거는 Content에 | 사용자 질문의 답변 근거가 되는 내용은 반드시 `<content>`에 존재한다(embedding_text 포함). |
| 자기완결 복원 | 검색 결과 하나(meta+content)만으로 원문 위치(파일/페이지/장·절/표·그림)와 문맥을 복원한다. |
| 텍스트 우선 추출 | 텍스트 레이어가 있으면 PDF 파싱을 우선한다. 전체 이미지화 금지. OCR/layout은 필요한 페이지·영역만. |
| 추출 방식 기록 | 모든 청크 meta에 `extract_method`(pdf_text|ocr|layout_analysis)를 기록한다. |
| Row 정규화 | 표 전체를 한 Chunk로 저장 금지. Row 단위로 분할하고 `<col name>`값으로 컬럼 의미를 보존한다. |
| 의미 자연어화 | 비텍스트는 OCR 평문이 아니라 의미를 자연어로 설명한다(스크린샷=사용자 행동, 순서도=관계 Mermaid). |
| XML / JSONL 분리 | 원본 복원(XML)과 검색(JSONL)을 분리 산출하고 chunk_id로 교차 복원한다. |
| 모델이 곧 계약 | pydantic 모델이 XML/JSONL 직렬화의 단일 진실이다. 모델 필드 ↔ XML 요소·속성은 명시 매핑표(§12.4)로 고정해 round-trip을 보장한다. |
| 결정성·멱등 | 동일 입력 → 동일 chunk_id·동일 산출물. LLM 경로만 캐싱+review로 결정화한다. ID 해시에 들어가는 float은 정규화 라운딩한다. |
| 비차단 신호 | 부분 실패·저신뢰는 전체를 실패시키지 않고 `review_required` 플래그로 격리한다(종료코드 0 유지). |

---

## 4. 전체 아키텍처 (Architecture)

파이프라인은 **"입력 사전 가드 → 페이지 진단 → 영역 라우팅 → 영역별 Chunk 생성 → 관계 빌드 →
XML/JSONL 분리 산출"** 의 단방향 흐름이다. 렌더(이미지화)는 OCR/Vision이 실제 필요한 페이지·
영역에서만 호출한다(전체 이미지화 금지).

```
[입력 PDF (절대경로, multipart는 Spring이 임시 저장)]
   │  document_id = "d_" + sha256(pdf_bytes)
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [0] 사전 가드  (guard.py)                                            │
│   파일 바이트 상한(max_input_mb) → 초과 시 종료코드 3                  │
│   doc.page_count 상한(max_pages, open 직후) → 초과 시 종료코드 5      │
│   페이지 MediaBox·이미지 픽셀폭탄 선검사(렌더 전 픽셀수 가드)          │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [1] 추출/진단  (extract/)                                             │
│   PyMuPDF get_text("rawdict"/"words") → 글리프 char/bbox/font/flags   │
│   (cid:N)/U+FFFD 토큰 비율로 깨짐 판정(§5.3)                          │
│   diagnose_page() → PageDiagnosis(verdict: ok_text|broken|scanned)    │
│   route_page()    → Region[] (text|table|figure|screenshot|flowchart)│
│      · 텍스트 영역 → pdf_text                                         │
│      · 표 영역 → pdfplumber 격자 무결성 → pdf_text 또는 ocr/layout    │
│      · 그림/도식/스샷/순서도 → render_region_png(clip=) → layout      │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [2] 구조 인식  (structure/)                                          │
│   규칙 마커(제N편/장/절/관/조, ①, ^\d+\., ^[가-하]\.) → heading 스택  │
│   의미 단위 청킹(max-chunk-chars) → text/list-item/warning/footnote  │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [3] 표 처리  (tables/)                                               │
│   RECOVER_SPANS(셀 bbox→격자 인덱싱→span 복원) →                      │
│   RESOLVE_SPANS(병합셀 반복채움) → FLATTEN_MULTIHEADER(다단헤더 결합) │
│   FILL_DOWN(세로병합 상속) → APPLY_SECTION_INHERITANCE(섹션 상속)     │
│   MERGE_CROSS_PAGE(분할표 논리 병합) → ROW_TO_CHUNK(table-row+embed)  │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [4] 비텍스트 의미화  (visuals/ + llm/)                               │
│   VisionProvider.describe() (OpenAI gpt-4o / offline 폴백)            │
│   infographic / screenshot(행동중심) / procedure-step /              │
│   flowchart(node) + flowchart-edge + graph(Mermaid)                  │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [5] 관계 그래프  (relations.py, 2-pass)                              │
│   Pass1: heading_path / parent / previous / next (읽기 순서)          │
│   Pass2: related_chunk_ids 양방향(표설명↔Record, 노드↔관계, 그림↔단계)│
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ [6] 산출  (serialize/)                                               │
│   xml_writer (lxml 자동 이스케이프) → chunks.xml   (원본 복원 정본)   │
│   jsonl_writer (embedding_text 파생) → chunks.jsonl (Vector DB 적재)  │
│   manifest (stdout 1줄 JSON + manifest.json)                         │
│   원자적 쓰기: temp → fsync → rename, manifest는 모든 rename 후 마지막 │
└───────────────┬──────────────────────────────────────────────────────┘
                ▼
[Spring ProcessBuilder] ── manifest.json 파일을 권위 소스로 → outputs 경로의 xml/jsonl 후속 소비
```

**XML은 원본 복원 정본, JSONL은 검색용 평면 뷰이며, 둘은 동일 chunk 집합에서 생성되어
chunk_id로 1:1 교차 복원된다.** 렌더는 OCR/Vision 대상 영역에서만 호출되어 "전체 이미지 변환
금지" 원칙을 충족한다. 산출물은 원자적 쓰기로 기록되고, Spring은 stdout 휴리스틱이 아니라
`manifest.json` **파일**을 권위 소스로 삼는다(§16.1).

---

## 문서 맵 (Document Map · 구현 단계 인덱스)

본 설계는 구현 시 불필요한 컨텍스트를 줄이기 위해 **얼개(본 파일) + 단계별 세부 파일**로 분리한다.
각 구현 step에서는 원칙적으로 **본 파일(§1~§4) + `00-foundation` + 해당 step 파일**만 참조하면 된다.
세부 파일은 [`pdf-to-xml-pipeline/`](./pdf-to-xml-pipeline/) 디렉터리에 있다.

| Step | 파일 | 담는 섹션 | 내용 | 선행 참조 |
| --- | --- | --- | --- | --- |
| 공통 기반 | [00-foundation](./pdf-to-xml-pipeline/00-foundation.md) | §11, §13, §15 | 데이터 모델 · chunk_id/멱등 · 신뢰도/review | (없음 — 항상 참조) |
| 공통 기반(산출물) | [08-output-schemas](./pdf-to-xml-pipeline/08-output-schemas.md) | §12 | XML 정본 · JSONL · manifest · 모델↔XML Round-Trip 매핑 | 00 |
| 1. 추출 | [01-extraction](./pdf-to-xml-pipeline/01-extraction.md) | §5 | 텍스트레이어 판정 · 영역 라우팅 · OCR | 00 |
| 2. 구조 인식 | [02-structure-recognition](./pdf-to-xml-pipeline/02-structure-recognition.md) | §6 | 마커 · heading 스택 | 00, 01 |
| 3. 표 처리 | [03-table-processing](./pdf-to-xml-pipeline/03-table-processing.md) | §7 | Row 정규화 · 병합셀 · 다단헤더 · 분할표 · embedding_text | 00, 01 |
| 4. 비텍스트 의미화 | [04-nontext-and-providers](./pdf-to-xml-pipeline/04-nontext-and-providers.md) | §8, §14 | 인포그래픽/스크린샷/순서도 + Vision/LLM Provider | 00, 01 |
| 5. 청킹 | [05-chunking](./pdf-to-xml-pipeline/05-chunking.md) | §9 | 의미 단위 청킹 | 00, 02 |
| 6. 관계 그래프 | [06-relations](./pdf-to-xml-pipeline/06-relations.md) | §10 | parent/prev/next/related/heading_path 2-pass | 00 (전 step 산출 청크 필요) |
| 7. Spring 연동 | [07-spring-integration](./pdf-to-xml-pipeline/07-spring-integration.md) | §16 | CLI · ProcessBuilder · 종료코드 · 배포 토폴로지 | 00 |

> 섹션 번호(§N)는 분리 후에도 **전역 고정 식별자**다. 파일 간 상호참조(예 `§12.4`, `§16.1`)는
> 위 표로 해당 파일을 찾는다. 디렉터리 구조·의존성·구성·구현계획·비기능·미정은 본 파일(§17~§22)에 남는다.

---

## 17. 디렉토리 구조 (Directory Layout)

기존 `backend/`(Java)·`frontend/`(React)는 무변경. Python은 저장소 루트 `pipeline/`에 격리한다.

```
pipeline/
  __init__.py
  __main__.py                # CLI 진입점(argparse). `python -m pipeline`
  version.py                 # PIPELINE_VERSION = "1.0.0"
  config.py                  # env/임계값 로딩(pydantic-settings)
  guard.py                   # 입력 사전 가드(바이트·페이지·픽셀폭탄), fd1→fd2 dup
  ids.py                     # make_document_id / make_chunk_id / norm_float / table_id / figure_id
  errors.py                  # PipelineError 계층 + 종료코드
  models.py                  # pydantic Chunk/Meta/Content/Document
  relations.py               # 2-pass 관계 그래프 빌더
  extract/                   # [1] 추출/진단
    pdf_text.py              # PyMuPDF: 텍스트+좌표+span, 텍스트레이어 판정(cid/FFFD)
    table_plumber.py         # pdfplumber: 표 셀/좌표 격자 + span 복원
    ocr.py                   # pytesseract+Pillow: 스캔/깨짐 영역만 OCR
    render.py                # 영역 PNG 렌더(clip=, 픽셀 가드), Vision/OCR 입력
    raw_span.py              # RawSpan 중간표현
    extract_router.py        # 페이지/영역 추출 방식 결정(백엔드 격리)
  structure/                 # [2] 구조 복원·정규화
    rules.py  chunker.py  normalize.py  heading.py
  tables/                    # [3] 표 → Row 정규화
    grid.py  spans.py  header.py  page_merge.py  row_records.py  confidence.py
  visuals/                   # [4] 비텍스트 의미화
    classify.py  describe.py  flowchart.py  screenshot.py
  llm/                       # provider 추상화(+offline 폴백)
    provider.py  openai_provider.py  offline_provider.py  cache.py
  serialize/                 # [5] 산출물
    xml_writer.py  jsonl_writer.py  manifest.py  validate.py  atomic_io.py
  schema/
    chunks.xsd               # (선택) 원본 구조 XML 검증 스키마
  py.typed
requirements.txt
README.md                    # 실행/Spring 연동/배포(컨테이너)/tesseract 설치 안내
tests/
  conftest.py
  golden/                    # 골든 코퍼스(텍스트 PDF → 고정 xml/jsonl, OCR 경로 분리)
  test_ids.py  test_relations.py  test_tables.py  test_xml_roundtrip.py
  test_model_schema.py  test_cli.py  test_determinism.py  test_coords.py
```

> 오케스트레이터 시그니처:
> `def extract_pdf(pdf_path, out_dir, asset_dir, document_id, vision, tesseract_cmd) -> ExtractionResult`
> (사전 가드 → 페이지 루프 → 영역 라우팅 → Chunk → 관계 → XML/JSON). Spring이 호출할
> 작업디렉토리 = 이 `pipeline/`의 부모(저장소 루트) 또는 venv/컨테이너 활성 경로.

---

## 18. 의존성 (Dependencies)

```text
# requirements.txt  (개발 Python 3.10+ / 운영 3.13 — 휠 가용성 P0 검증)
pydantic>=2.6,<3
pydantic-settings>=2.2,<3
PyMuPDF>=1.24,<2          # import fitz : 텍스트/좌표/페이지 PNG 렌더 (AGPL/상용 — §5.1 결정)
pdfplumber>=0.11,<0.12   # 표 격자/셀 좌표 + 병합 span 복원
pytesseract>=0.3.10,<0.4 # tesseract 래퍼(외부 바이너리 필요)
Pillow>=10.2,<11         # 이미지 처리(렌더/크롭/OCR 입력)
lxml>=5.1,<6             # XML 자동 이스케이프 직렬화
openai>=1.30,<2          # gpt-4o Vision/Chat. 키 없으면 offline 폴백
typing-extensions>=4.10
```

설치(Windows · 개발):

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```

### 외부 바이너리 — Tesseract OCR (pip 설치 불가)

`pytesseract`는 **Tesseract 실행파일과 언어팩**이 별도로 설치돼야 한다.

- Windows: UB-Mannheim 빌드 사용, 설치 시 **Korean 언어 데이터(kor)** 체크. 기본 경로
  `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- 언어팩: `kor.traineddata`, `eng.traineddata`가 `tessdata/`에 있어야 `--ocr-lang kor+eng` 동작.
- 경로 인식: PATH 추가 또는 `--tesseract-cmd`/`PIPELINE_TESSERACT_CMD`로 절대경로 주입. 미설치
  상태에서 OCR 필요 페이지를 만나면 종료코드 6(DependencyError) 또는 설정에 따라 layout/skip+review.
- 검증: `tesseract --version`(manifest에 버전 기록), `tesseract --list-langs`(kor 포함 확인).
- 배포 컨테이너(리눅스): `apt-get install -y tesseract-ocr tesseract-ocr-kor` — **운영 backend
  이미지(JRE-only)에 추가 설치가 필요**하다(§16.6 토폴로지 결정에 따라 Dockerfile/compose 변경).

> 라이선스: PyMuPDF=AGPL/상용(상용 배포 시 §5.1 결정 필수), pdfplumber=MIT, pytesseract=
> Apache-2.0, lxml=BSD, openai=Apache-2.0. Python 인터프리터 둘(`python`=3.10, `py`=3.13)이
> 있으므로, Spring `ProcessBuilder`가 호출할 정확한 인터프리터 경로(venv/컨테이너 절대경로)를
> 계약으로 단일 고정해 버전 혼선을 막는다. **운영 Python 버전(3.13)에서 PyMuPDF 등 휠 가용성을
> P0에서 실측 검증**한다(문서는 3.10에서만 확인됨).

---

## 19. 구성 (Configuration)

env 변수 + CLI 인자로 임계값/언어/한도/모델을 주입한다. 우선순위: **CLI 인자 > env > 기본값**.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIPELINE_", extra="ignore")
    # 임계값
    confidence_threshold: float = 0.6        # 미만 → review_required
    table_confidence_threshold: float = 0.7  # 미만 → 이미지 fallback
    text_preservation_min: float = 0.98      # 텍스트 보존율(검증)
    # 청킹
    max_chunk_chars: int = 1200; min_chunk_chars: int = 80
    # OCR
    ocr_lang: str = "kor+eng"; ocr_psm: int = 6; render_dpi: int = 300
    tesseract_cmd: str | None = None
    # 추출 라우팅(깨짐 판정 = cid/FFFD 토큰 비율, §5.3)
    glyph_recovery_min: float = 0.85; replacement_ratio_max: float = 0.02
    cid_fallback_ratio_max: float = 0.10; image_area_ratio_max: float = 0.6
    # LLM/Vision
    vision_mode: str = "auto"; offline: bool = False
    openai_model: str = "gpt-4o"; llm_temperature: float = 0.0
    llm_timeout_sec: int = 60; llm_cache_dir: str = ".cache/llm"
    # 리소스 한도(DoS 방어)
    max_input_mb: int = 100; max_pages: int = 300; max_chunks: int = 50000
    max_render_megapixels: int = 40; timeout_sec: int = 600; max_serialized_mb: int = 64
```

| env | 의미 | 기본 |
| --- | --- | --- |
| `OPENAI_API_KEY` | Vision/LLM 키(없으면 offline 강제) | (없음) |
| `OPENAI_MODEL` | Vision 모델 | gpt-4o |
| `PIPELINE_OCR_LANG` | tesseract 언어 | kor+eng |
| `PIPELINE_TESSERACT_CMD` | tesseract 절대경로 | PATH |
| `PIPELINE_CONFIDENCE_THRESHOLD` | 청크 신뢰 임계 | 0.6 |
| `PIPELINE_RENDER_DPI` | 렌더 DPI | 300 |
| `PIPELINE_MAX_INPUT_MB` / `PIPELINE_MAX_PAGES` | 입력 DoS 상한 | 100 / 300 |
| `PYTHONUTF8` / `PYTHONIOENCODING` | Windows UTF-8 | (Spring이 1/utf-8 설정) |

> 결정성을 위해 `ocr_psm`·`render_dpi`·`llm_temperature`·`norm_float` 라운딩은 고정값을 유지하고,
> 바꿀 때 `pipeline_version`을 올린다(멱등 경계). API 키는 `.env`(gitignore)·환경변수로만 주입하고
> 코드/로그/CLI 인자에 노출 금지. OpenAI/httpx SDK 로거는 진입 시 WARNING 이상으로 봉인한다(§14.2).

---

## 20. 단계별 구현 계획 (Phasing)

결정적(규칙·OCR) 구간을 먼저 완성하고 LLM은 나중. 각 단계는 독립 검증 가능한 산출물을 낸다.

**P0 — 골격 + 결정적 텍스트 경로 (offline 완전 동작)**
패키지·CLI·manifest·종료코드·errors / 입력 사전 가드(`guard.py`) / `models.py`(분리 Content
모델·needs_review·SourceLocation locator)+`ids.py`(`norm_float`) / extract.pdf_text(cid/FFFD
판정)+extract_router / structure(규칙·heading·청킹) → text/list-item/warning/footnote /
relations 2-pass / serialize(xml/jsonl/원자적 쓰기/라운드트립 + **모델 round-trip·json-schema
export 테스트**) / 좌표 어댑터 테스트 / 골든 코퍼스 회귀(OCR 경로 분리) + Spring 계약 + 배포
토폴로지 결정. → 텍스트 PDF를 키 없이 완전 처리, 멱등 보장. PyMuPDF 라이선스·Python 3.13 휠
검증을 P0에 포함.

**P1 — 표 Row 정규화 (검색 핵심)**
spans(셀 bbox→격자→span 복원)·grid·header(다단헤더 결합·섹션 상속)·page_merge(분할표
`[first,last]`)·row_records(col name + embedding_text)·confidence(게이트 → image fallback) /
table-row·table-note 청크 + 관계 Pass2 강화. → 표가 Row 단위로 검색·복원.

**P2 — OCR/layout (스캔본·깨짐 대응)**
extract.ocr·render(픽셀 가드)·router에 ocr/layout 분기 / 깨짐·스캔·표 붕괴 시에만 선택 적용
(전체 이미지화 금지) / DependencyError(tesseract 미설치) 종료코드 6 경로 / `tesseract_version`
기록·OCR 회귀 분리. → 스캔/깨짐 문서도 텍스트 확보.

**P3 — 비텍스트 의미화 (LLM provider)**
llm.provider+openai_provider(소켓 타임아웃·로깅 봉인)+offline_provider+cache / visuals.classify·
describe·flowchart(mermaid↔분해 동치성 게이트)·screenshot → infographic/screenshot/flowchart/
edge/graph 청크(자연어 설명·Mermaid·행동 중심) / 관계 related 마무리. → 그림/순서도/스크린샷 의미
검색. 키 없으면 offline 폴백.

**P4 — 통합·하드닝**
리소스 한도·타임아웃 워치독·프로세스 트리 종료·로그 위생(sk- 마스킹) / 배포 토폴로지 구현
(Dockerfile/compose, §16.6) / Spring `PdfPipelineRunner`/`PipelineProperties`/예외→HTTP 매핑 실제
구현(Java는 사용자 담당, 본 설계가 계약 확정) / CI: 결정성 회귀(offline 2회 byte-동일, OCR 분리),
LLM 캐시 멱등, 라운드트립·모델 round-trip 100%, 골든 F1.

> 의존성 순서: P0(결정적 골격) → P1(표) → P2(OCR) → P3(LLM) → P4(통합). P0만으로도 텍스트 PDF에
> 대해 end-to-end 가치(구조 보존 청크 + Vector DB jsonl)를 낸다.

---

## 21. 비기능 · 보안 (Non-Functional & Security)

| 분류 | 1차 설정 | 추후 |
| --- | --- | --- |
| 정확성 | 규칙 1차 우선, LLM은 검증 후 채택. 잘못 구조화보다 fallback이 안전 | 코퍼스 임계 튜닝 |
| 결정성 | 규칙·offline·직렬화 경로 골든 byte-동일 회귀(OCR은 환경 기록 후 정규화 비교 분리) | LLM 캐시 멱등 강화 |
| 안전성 | XXE 차단(`resolve_entities=false`, `no_network=true`, DTD 금지), 자산 내부 참조 잠금 | XSD 동결 시 keyref 검증 |
| 인젝션 경계 | 추출 텍스트·이미지·LLM 산출 = 외부 데이터(지시 아님). system에 미주입. nonce 구분자+충돌 시 구조화 포기 | 구분자 충돌 감지 강화 |
| 2차 인젝션 마킹 | 외부 데이터 유도 청크는 `needs_review`/외부출처 신호 마킹(소비측이 신뢰 경계 적용) | RAG 소비측 stored-injection 가드 협의 |
| 리소스 한도 | 입력 바이트·페이지·픽셀폭탄 사전 가드 + `max_chunks/serialized_mb`·타임아웃 워치독, 초과 시 거부/review | 병리적 PDF DoS 상한 튜닝 |
| 로그 위생 | XML 정본·LLM 원문·API 키(`sk-` 마스킹)·PII 절대 미로깅(샘플·해시만), SDK 로거 봉인 | PII 마스킹 규칙 확장 |

**보안 하드닝(반드시)**

- **입력 DoS 사전 가드**: 파이프라인 진입 즉시 (1) 파일 바이트 상한(`max_input_mb`), (2)
  `doc.page_count` 상한(`max_pages`, open 직후), (3) 렌더 전 픽셀수 가드(`max_render_megapixels`),
  (4) `colorspace=GRAY`·`alpha=False` Pixmap 축소, (5) 동시 렌더 1개 제한(§5.0). Spring도
  `ProcessBuilder` 호출 전 디스크 PDF 바이트/페이지를 재확인한다.
- **XXE/엔티티 폭탄 차단**: lxml 파싱은 `XMLParser(resolve_entities=False, no_network=True,
  load_dtd=False, dtd_validation=False)`. 입력 XML은 자가 생성물이고 DOCTYPE을 쓰지 않으므로
  엔티티 한도는 보조 방어.
- **직렬화 안전**: 모든 텍스트는 lxml `el.text`/`el.set`로만 주입(자동 이스케이프). 비유효 XML
  문자(`\x00-\x08\x0B\x0C\x0E-\x1F`)는 `clean_xml_text()`로 스트립. 직렬화→재파싱 라운드트립으로
  well-formedness + 텍스트 보존 + 모델 round-trip 검증(미달 종료코드 4).
- **프롬프트 인젝션**: Vision/LLM 입력은 외부 데이터 영역에만 두고 system 프롬프트로 경계 명시
  (§8.1). 스키마 위반·구분자 충돌 시 구조화 포기 + review. tool/json_schema 강제로 자유 텍스트
  의존 최소화.
- **비밀 관리**: API 키는 env로만 전달(커맨드라인 인자 금지, 프로세스 목록 노출 방지).
  로그·stdout·CLI 인자에 노출 금지. `openai`/`httpx`/`urllib3` 로거를 WARNING 이상으로 봉인하고
  `OPENAI_LOG` 미설정 강제(Authorization 헤더 누출 차단). stderr 흡수 시 Spring 측 `sk-` 마스킹.
- **stdout 무결성**: C-stdout(fd 1)을 fd 2로 dup 리다이렉트해 서드파티(MuPDF C-레벨) 경고가
  manifest 단일줄 규약을 오염하지 못하게 한다. Spring은 `manifest.json` 파일을 권위 소스로 사용.
- **프로세스 트리·자산 잠금**: 타임아웃 시 손자(tesseract/소켓)까지 트리 종료(§16.4).
  `source_location.asset_id`는 내부 `/api/v1/notices/assets/{sha256}`(64 hex) 참조만, 외부 URL/
  `data:` URI 금지.

---

## 22. 미정 / 추후 정의 (Open Questions)

- **임계 보정**: `glyph_recovery 0.85`·`cid_fallback 0.1`·`replacement 0.02` 등은 한국 규정 PDF
  표본 없이 정한 디폴트다. 산출 신호 경로는 §5.3으로 고정했으나 임계는 표본 코퍼스로 보정하고
  경계 케이스는 review로 노출.
- **PyMuPDF 라이선스 · Python 3.13 휠 — P0 결정**: AGPL/상용 듀얼 라이선스 처리(상용 구매 vs
  pypdfium2 교체)와 운영 Python 3.13에서의 휠 가용성을 P0에서 확정.
- **배포 토폴로지 — P0 결정**: 운영 backend(JRE-only 컨테이너)에 Python+PyMuPDF+tesseract+kor를
  어떻게 넣을지((A)/(B)/(C), §16.6)와 Dockerfile/compose 변경을 확정.
- **표 인식 한계**: 병합셀 span 복원(§7.0)·부분 괘선·셀 내 줄바꿈·세로쓰기에서 컬럼 정렬 오검출
  위험. pdfplumber strategy 튜닝·row-clip OCR 폴백·tableConfidence 임계의 코퍼스 튜닝이 필요.
- **embedding_text LLM 보강 채택 범위**: 결정적 템플릿을 1차로 두되, LLM 보강을 어느 content_type
  까지 적용할지(표 Record만 vs 비텍스트 전반)와 value-check 엄격도 결정.
- **Vector DB 종류·적재 워커**: 적재 대상 Vector DB(예: ChromaDB/pgvector)와 임베딩 모델, jsonl→
  upsert 워커의 소유(Spring vs 별도 워커) 결정. 본 설계는 적재 가능한 jsonl까지만 산출.
- **review_required 검토자 전달 채널**: 신호는 manifest·meta·jsonl metadata에 있으나, 검토자
  (프론트)에게 닿는 채널(관리자 라우트 vs 등록 워크플로 표시)은 Spring 측 결정 사항.
- **2차(stored) 프롬프트 인젝션**: 본 산출 `embedding_text`가 RAG 답변에 재주입될 때의 소비측
  방어(외부출처 마킹 활용)는 소비 파이프라인과 협의가 필요하다(본 설계는 신호만 제공).
- **DPI/성능 트레이드오프**: OCR 300~400dpi·표 영역 clip 렌더 다수 호출이 대용량/다페이지 PDF에서
  메모리·시간을 늘린다. 픽셀 가드·`max_pages`·렌더 캐시(sha256)·동시 렌더 1개 제한으로 완화하되
  상한 튜닝 필요.
- **회전/세로쓰기 표 헤더**: 회전 페이지 transform 환산과 세로쓰기 헤더 인식의 한계 — 무리한
  구조화보다 image fallback + review 위임 임계 튜닝. CropBox 비-0 오프셋·rotation 환산 테스트 포함.
