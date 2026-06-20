# 공통 기반 — 데이터 모델·식별자·신뢰도 (PDF → RAG Chunk 파이프라인)

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §11~§13, §15 · 선행 참조: 없음 — 모든 step의 공통 계약(거의 항상 함께 참조)
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 11. 데이터 모델 (Data Model, pydantic v2)

설계 원칙: **Meta = 구조·출처·관계만**, **Content = 의미만**, **타입별 Content 변형**. 모든 모델
`model_config = ConfigDict(extra="forbid")`로 스키마 드리프트를 차단한다. **모델이 곧 XML/JSONL
직렬화의 단일 진실**이며, 모든 content_type의 XML 예시(§12.1)는 본 절 모델로 직렬화·역직렬화
가능해야 한다(필드 ↔ XML 매핑은 §12.4).

### 11.1 Enum / 기하 / 출처

```python
class ContentType(str, Enum):
    TEXT="text"; TABLE_ROW="table-row"; TABLE_NOTE="table-note"; LIST_ITEM="list-item"
    PROCEDURE_STEP="procedure-step"; INFOGRAPHIC="infographic"; SCREENSHOT="screenshot"
    FLOWCHART="flowchart"; FLOWCHART_EDGE="flowchart-edge"; GRAPH="graph"
    WARNING="warning"; FOOTNOTE="footnote"; REFERENCE="reference"

class ExtractMethod(str, Enum):
    PDF_TEXT="pdf_text"; OCR="ocr"; LAYOUT_ANALYSIS="layout_analysis"

class BBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1)
    x0: float; y0: float; x1: float; y1: float          # PDF point, 좌상단 원점

class SourceLocation(BaseModel):
    """검색 결과 하나로 원문 위치를 복원하기 위한 자기완결 출처(장·절·항 포함)."""
    model_config = ConfigDict(extra="forbid")
    file_name: str
    document_id: str
    page_no: int | None
    page_range: tuple[int, int] | None
    bbox: BBox | None                                   # pdf_text/layout 필수(아래 validator)
    extract_method: ExtractMethod
    heading_path: list[str] = Field(default_factory=list)  # 장·절·항 자기완결(출처를 SourceLocation 단독으로)
    locator: str | None = None                          # heading_path를 " > "로 평탄화한 표시용 경로
    dpi: int | None
    asset_id: str | None                                # 렌더 PNG sha256(64 hex)
    char_range: tuple[int, int] | None                  # pdf_text 시 페이지 내 글리프 인덱스
    table_id: str | None
    figure_id: str | None
    transform: list[float] | None                       # 회전 정규화 행렬

    @model_validator(mode="after")
    def _locatable(self):
        # 위치 복원 보장: bbox 또는 char_range 중 하나는 항상 존재(둘 다 없으면 거부)
        if self.bbox is None and self.char_range is None:
            raise ValueError("bbox 또는 char_range 중 하나는 필수(위치 복원 보장)")
        return self
```

`SourceLocation`은 `heading_path`/`locator`를 보유해 **"어떤 장·절·항인지"를 SourceLocation
단독으로 자기완결**한다(SPEC '출처는 Meta만으로'). XML의 `source_location/@locator`(§12.1)는 이
`locator` 필드와 1:1 정합한다.

### 11.2 Meta (구조·출처·관계만)

```python
class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    document_id: str
    file_name: str
    page_no: int | None = Field(default=None, ge=1)
    page_range: tuple[int, int] | None = None
    content_type: ContentType
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    item: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    table_id: str | None = None
    figure_id: str | None = None
    extract_method: ExtractMethod
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBox | None = None
    parent_chunk_id: str | None = None
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    related_chunk_ids: list[str] = Field(default_factory=list)
    source_location: SourceLocation
    # 비차단 검토 신호(SPEC 정규 필드는 아니나 본 설계의 핵심 신호 — 모델·meta·jsonl 일관)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self):
        if self.page_no is None and not self.page_range:
            raise ValueError("page_no 또는 page_range 중 하나는 필수")
        # 위치 복원 강도 균일화: pdf_text/layout_analysis 청크는 bbox 또는 char_range 보장
        if self.extract_method in (ExtractMethod.PDF_TEXT, ExtractMethod.LAYOUT_ANALYSIS):
            if self.bbox is None and self.source_location.char_range is None:
                raise ValueError("pdf_text/layout 청크는 bbox 또는 char_range 필수")
        # page_range만 있는 행은 자기 행의 단일 page를 bbox.page로 보유(분할표 Record)
        if self.page_no is None and self.page_range and self.bbox is not None:
            assert self.page_range[0] <= self.bbox.page <= self.page_range[1]
        return self
```

**Meta 필드 명세**(SPEC의 전 필드 포함):

| 필드 | 타입 | 필수 | 의미 | 예시 |
| --- | --- | --- | --- | --- |
| chunk_id | str | 필수 | 전역 고유 결정적 ID(sha256 기반). Vector DB PK | `c_3a7f...0012` |
| document_id | str | 필수 | 소속 문서 결정적 ID(PDF 콘텐츠 해시) | `d_9f2c...e1` |
| file_name | str | 필수 | 원본 파일명 | `정책자금_운용지침.pdf` |
| page_no | int\|null | 조건부 | 단일 페이지(1-base). page_range 없으면 필수 | `12` |
| page_range | int[]\|null | 조건부 | 분할표 등 다중 페이지. page_no 없으면 필수 | `[12,13]` |
| content_type | enum | 필수 | 13종 청크 타입 | `table-row` |
| chapter/section/subsection | str\|null | 선택 | 장/절/관(소절) | `제3장` / `2절` |
| item | str\|null | 선택 | 목록·항목 마커 | `가.` / `1.` |
| heading_path | str[] | 필수(빈배열 허용) | 루트→현재 위계 경로(문맥 복원 핵심) | `["제3장","2절","OCR 처리"]` |
| table_id | str\|null | 조건부 | table-row/table-note 필수 | `tbl_0003` |
| figure_id | str\|null | 조건부 | infographic/screenshot/flowchart/edge/graph 필수 | `fig_0002` |
| extract_method | enum | 필수 | pdf_text\|ocr\|layout_analysis | `pdf_text` |
| confidence | float[0,1] | 필수 | 추출 신뢰도. 임계 미만 시 review_required | `0.94` |
| bbox | BBox\|null | 조건부(pdf_text/layout 필수, 그 외 권장) | 페이지 내 좌표(point) | `{page:12,x0:..}` |
| parent_chunk_id | str\|null | 선택 | 상위 구조 청크 | `c_tbl_0003_hdr` |
| previous/next_chunk_id | str\|null | 선택 | 문서 순서상 직전/직후 | `c_..._0013` |
| related_chunk_ids | str[] | 필수(빈배열 허용) | 연관 청크 | `["c_note_a","c_row_b"]` |
| source_location | SourceLocation | 필수 | 자기완결 출처(파일/페이지/장·절·항/표·그림/추출방식) | (§11.1) |
| needs_review | bool | 필수(기본 false) | 비차단 검토 신호. jsonl metadata에도 동반 | `true` |
| review_reasons | str[] | 필수(빈배열 허용) | 검토 사유 코드 | `["low_confidence"]` |

조건부 필수 규칙(validator): `content_type ∈ {table-row, table-note}` → `table_id` 필수;
`content_type ∈ {infographic, screenshot, flowchart, flowchart-edge, graph}` → `figure_id` 필수;
`page_no XOR page_range` 최소 하나 필수; `extract_method ∈ {pdf_text, layout_analysis}` → bbox
또는 char_range 필수.

> **`needs_review`는 SPEC 정규 필드는 아니나 본 설계의 핵심 비차단 신호다.** 모델·`meta`·jsonl
> `metadata`·`manifest` **네 곳 모두에 일관되게 실리도록** Meta 정규 필드로 승격했다(§5.6/§8/
> §12.2/§15의 "meta에 needs_review 기록" 문구와 모델이 일치). `extra="forbid"` 하에서도 직렬화
> 가능하다.

### 11.3 Content (타입별 변형, discriminated union)

XML 예시(§12.1)의 풍부한 자식·속성 구조를 모델 차원에서 표현 가능하도록, 스크린샷/인포그래픽을
**별도 모델로 분리**하고 절차/엣지를 보강한다. 모든 모델 `extra="forbid"` 하에서 직렬화·
역직렬화된다.

```python
class TextContent(BaseModel):       kind: Literal["text"]="text";        text: str
class ListItemContent(BaseModel):   kind: Literal["list-item"]="list-item"; marker: str|None=None; text: str

class Col(BaseModel):               name: str; value: str
class TableRowContent(BaseModel):
    kind: Literal["table-row"]="table-row"
    cols: list[Col]                                     # 반드시 <col name=..>값
    section_path: list[str] = Field(default_factory=list)
    embedding_text: str                                # 표 Record 필수
class TableNoteContent(BaseModel):  kind: Literal["table-note"]="table-note"; text: str

# 절차: branch 분기를 데이터모델로 표현(SPEC '절차 branch 분기')
class Branch(BaseModel):            on: str; target_step_id: str | None = None
class ProcedureStepContent(BaseModel):
    kind: Literal["procedure-step"]="procedure-step"
    step_no: int | None = None
    step_label: str | None = None
    actions: list[str] = Field(default_factory=list)    # <action> 0..N
    detail: str | None = None
    branches: list[Branch] = Field(default_factory=list)  # <branch on=..>
    ocr_text: str | None = None

# 순서도: 노드/엣지/그래프. relation 필드명이 곧 <relation> 요소(§12.4)
class FlowchartNodeContent(BaseModel):
    kind: Literal["flowchart"]="flowchart"
    node_id: str; node_type: str | None = None; label: str; semantics: str
class FlowchartEdgeContent(BaseModel):
    kind: Literal["flowchart-edge"]="flowchart-edge"
    from_node: str; to_node: str; condition: str | None = None
    relation: str                                       # <relation> (이전 'text'에서 개명)
class GraphContent(BaseModel):
    kind: Literal["graph"]="graph"; notation: str = "mermaid"; mermaid: str; summary: str

# 스크린샷: 사용자 행동 단위 분해(SPEC '행동 단위')
class Action(BaseModel):            verb: str; target: str; value: str | None = None; state: str | None = None
class Emphasis(BaseModel):          target: str; meaning: str
class ScreenshotContent(BaseModel):
    kind: Literal["screenshot"]="screenshot"
    screen_name: str | None = None
    purpose: str                                        # 최소 한 줄(OCR 단독 저장 금지)
    actions: list[Action] = Field(default_factory=list)
    emphasis: list[Emphasis] = Field(default_factory=list)
    ocr_text: str | None = None

# 인포그래픽: data_points 0..N(SPEC 'data_points')
class DataPoint(BaseModel):         name: str; value: str
class InfographicContent(BaseModel):
    kind: Literal["infographic"]="infographic"
    info_kind: str | None = None                        # 개념도|통계그래픽|아이콘다이어그램 (XML @kind)
    summary: str                                        # 핵심 의미(필수)
    reading: str | None = None
    data_points: list[DataPoint] = Field(default_factory=list)
    ocr_text: str | None = None

class WarningContent(BaseModel):    kind: Literal["warning"]="warning"; level: str|None=None; text: str
class FootnoteContent(BaseModel):   kind: Literal["footnote"]="footnote"; ref_marker: str|None=None; text: str
class ReferenceContent(BaseModel):  kind: Literal["reference"]="reference"; text: str; target_hint: str|None=None

Content = Annotated[
    Union[TextContent, ListItemContent, TableRowContent, TableNoteContent,
          ProcedureStepContent, FlowchartNodeContent, FlowchartEdgeContent, GraphContent,
          ScreenshotContent, InfographicContent, WarningContent, FootnoteContent, ReferenceContent],
    Field(discriminator="kind")]

class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: Meta
    content: Content

    @model_validator(mode="after")
    def _type_alignment(self):       # discriminator 1:1 → content.kind == meta.content_type
        if self.content.kind != self.meta.content_type.value:
            raise ValueError(f"content_type({self.meta.content_type.value}) != content.kind({self.content.kind})")
        return self
```

`Content`는 `kind` 기반 discriminated union으로 타입별 변형을 강제한다. 스크린샷·인포그래픽을
별도 모델로 분리해 **discriminator가 모든 13종에서 1:1**이 되었으므로, union·JSON 스키마 export·
`_type_alignment`가 모두 단순·견고해진다(이전 `DescribedVisualContent`의 다중 Literal 특례 분기
제거). `model_dump(mode="json")`/json-schema 라운드트립 테스트를 P0 골든에 포함한다(중첩
discriminated-union 스키마 export 경로 검증).

---


## 12. 산출물 스키마 (Output Schemas)

> 분량 분리: XML 정본·JSONL·manifest 스키마와 모델↔XML Round-Trip 매핑 상세는
> [08-output-schemas.md](08-output-schemas.md) 참조.

## 13. chunk_id · 멱등성 (Identifiers & Idempotency)

목표: 동일 입력(동일 PDF 바이트 + 동일 pipeline_version + 동일 config + 동일 환경) → 동일 ID·
동일 XML·동일 jsonl. ID에 타임스탬프·UUID·난수 절대 미포함. **ID 해시에 들어가는 모든 float은
정규화 라운딩**(아래)으로 부동소수 미세변동이 ID를 흔들지 않게 한다.

### 13.1 ID 생성

```python
def make_document_id(pdf_bytes: bytes) -> str:
    return "d_" + hashlib.sha256(pdf_bytes).hexdigest()        # 콘텐츠 주소

def norm_float(x: float) -> str:
    return f"{round(x, 1):.1f}"                                # bbox/격자 좌표 0.1pt 라운딩(canonical)

def make_chunk_id(document_id, content_type, page_anchor, structural_path, norm_content, seq) -> str:
    h = hashlib.sha256()
    for part in (document_id, content_type, page_anchor, structural_path, norm_content, str(seq)):
        h.update(part.encode("utf-8")); h.update(b"\x1f")     # 구분자
    return "c_" + h.hexdigest()[:24]                          # 24 hex 절단(충돌 무시 가능)
```

- `page_anchor`: `"p12"` 또는 분할표 `"p12-13"`.
- `structural_path`: heading_path를 `\x1f`로 join + table_id/figure_id 접두(`tbl_0003#`).
- **`norm_content` — content_type별 정규화 규칙(결정성의 핵심)**: 호출자가 타입에 따라 **결정
  가능한 부분만** 넣는다. 아래 표가 두 절(§13.1 시그니처 ↔ §13.2 LLM 청크) 모순을 제거한다.

| content_type 군 | `norm_content`에 넣는 값 |
| --- | --- |
| 결정적(text/list-item/table-row/table-note/warning/footnote/reference) | 정규화 콘텐츠(공백 정리·유니코드 NFC). 표 Record는 정렬된 `name=value` 직렬화 |
| 비결정(vision/llm: infographic/screenshot/flowchart/flowchart-edge/graph/procedure-step) | `""`(빈 문자열). 대신 `structural_path`에 `figure_id` + 결정적 `seq`만 사용 |

  즉 결정적 타입은 콘텐츠를 해시에 포함하고, Vision/LLM 타입은 **설명 텍스트를 해시에서 제외**해
  미세 변동이 ID를 흔들지 않게 한다(같은 함수, 호출자 분기 규칙으로 일관화).
- `seq`: 동일 (page, structural_path) 내 형제 순서. 추출기는 항상 `(page, y, x)` 정렬로 순회해
  결정적.
- `table_id` = `"tbl_" + sha256(doc_id + page_anchor + canonical_격자_서명)[:8]`. 격자 서명은
  **라운딩·정렬된 셀 경계**(`norm_float`)로 canonical 직렬화(분할표도 동일 서명이면 동일).
- `figure_id` = `"fig_" + sha256(doc_id + page_anchor + norm_bbox)[:8]`. `norm_bbox`는 `norm_float`
  적용 좌표.
- table-row 가독 별칭 `c_{table_id}_r_{seq:03d}`를 허용하되 정본 PK는 sha256 절단값(예시 XML은
  가독 별칭 사용).

### 13.2 멱등 경계

| 구간 | 결정성 | 비고 |
| --- | --- | --- |
| 추출(pdf_text) | 완전 결정 | PyMuPDF/pdfplumber 추출 + `(page,y,x)` 정렬 |
| 구조·정규화·관계 | 완전 결정 | 규칙 엔진 + `sorted(set())` 마감 + float 라운딩 |
| OCR(tesseract) | **환경 고정 시 재현적** | 동일 이미지·lang·psm·dpi **+ 동일 tesseract/traineddata/빌드** → 동일 텍스트. 버전 의존성 인정 |
| ID·직렬화 | 완전 결정 | sha256+seq+`norm_float`. `generated_at`는 XML 속성에만, chunk_id 해시 미포함 |
| Vision/LLM 의미화 | 비결정 | 콘텐츠 주소 캐시로 결정화, 설명은 ID 해시 제외 |

**OCR 결정성의 환경 의존성**: Tesseract 출력은 동일 입력이라도 **버전·언어팩(traineddata)
버전·빌드(OMP 스레드/SIMD)**에 따라 달라질 수 있어 "완전 결정"이 아니라 "환경 고정 시
재현적(reproducible-given-env)"으로 격하한다. 따라서 **골든 byte-동일 회귀 대상은 pdf_text/규칙/
직렬화 경로로 한정**하고, OCR/offline-OCR 청크는 `tesseract_version`을 manifest에 기록한 뒤
**정규화 후 비교 또는 tolerance 비교**로 분리한다(환경 차이로 CI가 깨지지 않게).

**LLM 결정화**: 캐시 키 = `sha256(model_id + prompt_version + image_sha256 또는 입력텍스트_sha256
+ temperature)`. `temperature=0` + 출력 정규화(NFC) 후 `--outdir/.cache/llm/`에 기록. 캐시 미스
(최초 실행)는 비결정 가능 → 해당 청크는 confidence 낮아 `review_required`. **LLM 설명 텍스트는
chunk_id 해시 입력에서 제외**하고 `figure_id+seq`만 사용(§13.1 규칙표 — 설명 미세 변동이 ID를
흔들지 않게).

> 텍스트 레이어 PDF(offline 모드, pdf_text 경로)는 결정적 구간만으로 끝나므로 **골든 파일 회귀로
> 100% 멱등 고정**한다(OCR 경로 제외). `pipeline_version`·정규화 규칙·프롬프트 변경 시 버전을
> 올리고 **전체 재색인**(부분 갱신 금지). Spring은 manifest의 `pipeline_version` +
> `source_sha256`으로 "이미 적재됨"을 판정해 중복 작업을 스킵한다. 골든 테스트에 "PyMuPDF 패치
> 버전 차이"에 대한 ID 안정성 케이스(float 라운딩)를 포함한다.

---

## 15. 신뢰도 · review_required (Confidence)

### 15.1 confidence 산출 (청크별 0~1)

- 베이스(extract_method): pdf_text=0.95, layout_analysis=0.8, vision(LLM 의미화)=0.7,
  ocr/offline=0.3.
- 가감산: Vision 스키마 위반/부분파싱 −0.3; 그래프 dangling edge·decision 분기<2·mermaid↔분해
  청크 집합 불일치·절차 결번 −0.2; 스크린샷 action 0개·인포그래픽 summary 공백 −0.3; OCR 보존만
  있고 의미 설명 없음 → 0.3 상한.
- 문서 confidence = 청크 confidence 가중 집계(텍스트 비중 큰 문서 높게). meta에 청크/문서 각각
  기록.

### 15.2 review_required 발동 (비차단)

하나라도 충족 시 `meta.needs_review=true`(+ `review_reasons`에 사유 코드):

1. 청크 confidence < 임계(권장 0.7) → `low_confidence`.
2. Vision/LLM 산출이 스키마 검증·구조 규칙(노드-엣지 정합, mermaid↔분해 청크 동치, 단계 연속성,
   표 격자 정합) 미통과 → 규칙/OCR 폴백 채택 → `schema_fallback`.
3. offline 폴백 경로로 생성된 비텍스트 청크 → `offline_fallback`.
4. tableConfidence < 임계로 image fallback → `table_fallback`, 또는 스크린샷/순서도 구분자
   충돌로 구조화 포기 → `delimiter_conflict`.
5. OCR 단독(의미 설명 생성 실패), 또는 인젝션 의심 패턴 감지로 산출 거부 → `injection_suspect`.
6. LLM 보강이 개입한 모든 청크(temperature=0이어도 비결정 가능) → `llm_assisted`.

**원칙**: review_required는 **비차단 신호**다. 파이프라인은 종료코드 0으로 정상 산출하고 플래그만
세운다(적재를 막지 않음). 플래그는 **meta(`needs_review`/`review_reasons`) · jsonl metadata(평탄
dump) · manifest(`review_required` 집계) 세 곳에 일관 기록**한다(§11.2 모델이 이를 보장). 결정성
회귀는 규칙·offline 단독 경로만 대상으로 하고 Vision/LLM·OCR 경로는 분리한다(§13.2).

---
