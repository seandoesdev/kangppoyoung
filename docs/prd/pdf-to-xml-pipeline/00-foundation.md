# 공통 기반 — 데이터 모델·산출물·식별자·신뢰도 — PDF → RAG Chunk 파이프라인

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

동일 chunk 집합에서 **원본 복원용 XML**과 **검색용 JSONL**을 분리 생성하고, 둘은 chunk_id로
1:1 교차 복원된다. 추가로 **manifest**를 산출한다. 모든 산출은 **원자적 쓰기**(temp → fsync →
rename)로 기록하고, manifest는 xml/jsonl rename 성공 **후** 마지막에 쓴다(§16.1).

### 12.1 원본 구조 보존 XML (chunks.xml)

루트 `<document>` → `<chunk id="...">` → `<meta>` / `<content>`. lxml `el.text=value`/`el.set`로만
주입해 `&`/`<`/`>`/`"`/`'` 자동 이스케이프(문자열 조립 금지). 파싱은
`XMLParser(resolve_entities=False, no_network=True, load_dtd=False)`로 XXE 차단. 직렬화는
**§11.3 모델 → §12.4 매핑표**에 따른 결정적 변환이다.

```python
def to_chunks_xml(chunks: list[Chunk]) -> bytes: ...   # 모델→XML(§12.4 매핑) 직렬화
```

여러 content_type 예시(모두 §11.3 모델로 직렬화·역직렬화 가능):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<document id="d_9f2c...e1" file_name="정책자금_운용지침.pdf"
          source_sha256="9f2c...e1" pipeline_version="1.0.0"
          generated_at="2026-06-16T00:00:00Z">

  <!-- 1) 일반 본문 -->
  <chunk id="c_..._0007">
    <meta>
      <document_id>d_9f2c...e1</document_id>
      <file_name>정책자금_운용지침.pdf</file_name>
      <page_no>12</page_no>
      <content_type>text</content_type>
      <chapter>제3장</chapter><section>2절</section><subsection>2.1 데이터 수집</subsection>
      <heading_path><h>제3장</h><h>2절</h><h>2.1 데이터 수집</h><h>OCR 처리</h></heading_path>
      <extract_method>pdf_text</extract_method>
      <confidence>0.97</confidence>
      <bbox page="12" x0="72.0" y0="120.4" x1="523.0" y1="180.2"/>
      <parent_chunk_id>c_..._sec_2_1</parent_chunk_id>
      <previous_chunk_id>c_..._0006</previous_chunk_id>
      <next_chunk_id>c_..._0008</next_chunk_id>
      <related_chunk_ids/>
      <needs_review>false</needs_review>
      <source_location file_name="정책자금_운용지침.pdf" page_no="12"
                       extract_method="pdf_text"
                       locator="제3장 &gt; 2절 &gt; 2.1 데이터 수집 &gt; OCR 처리"/>
    </meta>
    <content>
      <text>스캔본은 페이지 단위로 OCR을 적용하며 텍스트 레이어가 있으면 우선 추출한다.</text>
    </content>
  </chunk>

  <!-- 2) 목록 항목 -->
  <chunk id="c_..._0021">
    <meta><content_type>list-item</content_type><item>가.</item> ... </meta>
    <content><list-item marker="가.">신청서 1부를 제출한다.</list-item></content>
  </chunk>

  <!-- 3) 표 Record (한 Row=한 Chunk, col name 필수, 섹션 상속, embedding_text) -->
  <chunk id="c_tbl_0003_r_002">
    <meta>
      <content_type>table-row</content_type>
      <table_id>tbl_0003</table_id>
      <page_range><p>12</p><p>13</p></page_range>
      <bbox page="13" x0="72.0" y0="300.1" x1="523.0" y1="330.5"/>
      <extract_method>pdf_text</extract_method><confidence>0.94</confidence>
      <parent_chunk_id>c_tbl_0003_hdr</parent_chunk_id>
      <related_chunk_ids><id>c_tbl_0003_note_1</id><id>c_tbl_0003_sec_1</id></related_chunk_ids>
      <needs_review>false</needs_review>
      ...
    </meta>
    <content>
      <table-row>
        <section-path><s>1. 사출·프레스산업</s></section-path>
        <col name="산업분류코드">1234</col>
        <col name="산업명">자동차 부품 제조업</col>
        <col name="지원정보_지원금액">5억원 이내</col>
        <col name="섹션">사출·프레스산업</col>
        <embedding_text>자동차 부품 제조업은 산업분류코드 1234에 해당하며 사출·프레스산업 섹션에 포함되고 지원금액은 5억원 이내다.</embedding_text>
      </table-row>
    </content>
  </chunk>

  <!-- 4) 표 주석 -->
  <chunk id="c_tbl_0003_note_1">
    <meta><content_type>table-note</content_type><table_id>tbl_0003</table_id> ... </meta>
    <content><table-note>지원금액은 부가세 제외 기준이다.</table-note></content>
  </chunk>

  <!-- 5) 인포그래픽 (의미 설명, OCR 보조) -->
  <chunk id="c_..._fig_2">
    <meta><content_type>infographic</content_type><figure_id>fig_0002</figure_id>
          <extract_method>layout_analysis</extract_method><confidence>0.8</confidence> ... </meta>
    <content>
      <infographic kind="통계그래픽">
        <summary>연도별 융자 한도 추이를 막대그래프로 보여주며 2024년에 한도가 5억원으로 상향됨을 강조한다.</summary>
        <reading>가로축은 연도(2022~2024), 세로축은 융자 한도(억원). 2022년 3억, 2023년 4억, 2024년 5억으로 매년 증가한다.</reading>
        <data-point name="2024년 융자한도">5억원</data-point>
        <ocr-text>융자 한도 추이 3 4 5 2022 2023 2024</ocr-text>
      </infographic>
    </content>
  </chunk>

  <!-- 6) 절차 단계 (actions/detail/branch/ocr-text) -->
  <chunk id="c_..._proc_2">
    <meta><content_type>procedure-step</content_type><figure_id>fig_0005</figure_id>
          <parent_chunk_id>c_..._proc_root</parent_chunk_id>
          <previous_chunk_id>c_..._proc_1</previous_chunk_id>
          <next_chunk_id>c_..._proc_3</next_chunk_id> ... </meta>
    <content>
      <procedure-step step-no="2" step-label="신청서 작성">
        <action>사업자등록번호와 대표자명을 입력한다.</action>
        <detail>필수 항목은 빨간 별표로 표시된다.</detail>
        <branch on="금액 5억 초과" target-step-id="c_..._proc_5">자동 승인 대신 심사 단계로 분기한다.</branch>
        <ocr-text>신청서 작성 사업자등록번호 대표자명</ocr-text>
      </procedure-step>
    </content>
  </chunk>

  <!-- 7) 스크린샷 (사용자 행동 중심) -->
  <chunk id="c_..._shot_1">
    <meta><content_type>screenshot</content_type><figure_id>fig_0010</figure_id>
          <extract_method>layout_analysis</extract_method> ... </meta>
    <content>
      <screenshot screen-name="신청서 입력 화면">
        <purpose>지원금 신청 정보를 입력하는 화면이다.</purpose>
        <action verb="입력" target="사업자등록번호" value="000-00-00000"/>
        <action verb="체크" target="개인정보 동의 체크박스" state="checked"/>
        <action verb="클릭" target="다음 버튼"/>
        <emphasis target="필수 항목">빨간 별표는 필수 입력 항목을 의미한다.</emphasis>
        <ocr-text>지원금 신청 사업자등록번호 동의 다음</ocr-text>
      </screenshot>
    </content>
  </chunk>

  <!-- 8) 순서도 그래프 + 노드 + 관계(Mermaid) -->
  <chunk id="c_..._graph_3">
    <meta><content_type>graph</content_type><figure_id>fig_flow_3</figure_id> ... </meta>
    <content>
      <graph notation="mermaid">
        <mermaid>flowchart TD
  n1["신청 접수"] --> n3{"금액 5억 초과?"}
  n3 -- 예 --> n5["심사위 회부"]
  n3 -- 아니오 --> n4["자동 승인"]</mermaid>
        <summary>신청을 접수하고 금액이 5억을 초과하면 심사위에 회부, 이하면 자동 승인하는 흐름이다.</summary>
      </graph>
    </content>
  </chunk>
  <chunk id="c_..._node_n3">
    <meta><content_type>flowchart</content_type><figure_id>fig_flow_3</figure_id>
          <parent_chunk_id>c_..._graph_3</parent_chunk_id>
          <related_chunk_ids><id>c_..._edge_2</id></related_chunk_ids> ... </meta>
    <content><flowchart node-id="n3" node-type="decision">
      <label>금액 5억 초과?</label>
      <semantics>신청 금액이 5억원을 초과하는지 판단하는 결정 노드다.</semantics>
    </flowchart></content>
  </chunk>
  <chunk id="c_..._edge_2">
    <meta><content_type>flowchart-edge</content_type><figure_id>fig_flow_3</figure_id>
          <parent_chunk_id>c_..._graph_3</parent_chunk_id>
          <related_chunk_ids><id>c_..._node_n3</id><id>c_..._node_n5</id></related_chunk_ids> ... </meta>
    <content><flowchart-edge from="n3" to="n5" condition="예">
      <relation>금액이 5억을 초과하면 n3에서 n5(심사위 회부)로 진행한다.</relation>
    </flowchart-edge></content>
  </chunk>

  <!-- 9) 각주 / 경고 / 참조 -->
  <chunk id="c_..._fn_1">
    <meta><content_type>footnote</content_type> ... </meta>
    <content><footnote ref-marker="*1">대분류는 한국표준산업분류(KSIC) 기준이다.</footnote></content>
  </chunk>
  <chunk id="c_..._warn_1">
    <meta><content_type>warning</content_type> ... </meta>
    <content><warning level="caution">제출 후에는 정정이 불가하므로 주의한다.</warning></content>
  </chunk>
  <chunk id="c_..._ref_1">
    <meta><content_type>reference</content_type> ... </meta>
    <content><reference target-hint="별표 1">융자 한도는 별표 1을 참조한다.</reference></content>
  </chunk>
</document>
```

> 예시의 `&gt;`는 `locator` 속성 안의 `>`가 lxml `el.set()`로 자동 이스케이프됨을 보인다. 모든
> 텍스트는 `el.text`/`el.set`로만 주입하고 f-string XML 조립을 금지한다. 직렬화 후
> `etree.fromstring`(secure parser)로 재파싱해 well-formedness + 텍스트 보존 + **모델
> round-trip**(XML→모델 역파싱 동치)을 검증하며, 실패 시 종료코드 4.

### 12.2 Vector DB 적재 JSONL (chunks.jsonl)

한 줄 = 한 청크 = `{chunk_id, content_type, embedding_text, metadata}`(UTF-8,
`ensure_ascii=false`). `metadata`는 Meta 전체 평탄 dump(`model_dump(mode="json")`)이므로
`needs_review`/`review_reasons`도 jsonl에 함께 실린다.

```python
def to_vector_records(chunks: list[Chunk]) -> list[dict]: ...   # 최소 스키마 + 출처꼬리표
```

한 줄 예시(가독을 위해 줄바꿈했으나 실제는 1줄):

```json
{"chunk_id":"c_tbl_0003_r_002","document_id":"d_9f2c...e1","content_type":"table-row","embedding_text":"자동차 부품 제조업은 산업분류코드 1234에 해당하며 사출·프레스산업 섹션에 포함되고 지원금액은 5억원 이내다. (출처: 정책자금_운용지침.pdf p.12-13, 제3장 > 지원 산업 목록 > 1. 사출·프레스산업)","metadata":{"document_id":"d_9f2c...e1","file_name":"정책자금_운용지침.pdf","page_no":null,"page_range":[12,13],"content_type":"table-row","heading_path":["제3장","2절","지원 산업 목록","1. 사출·프레스산업"],"chapter":"제3장","section":"2절","subsection":null,"item":null,"table_id":"tbl_0003","figure_id":null,"extract_method":"pdf_text","confidence":0.94,"bbox":{"page":13,"x0":72.0,"y0":300.1,"x1":523.0,"y1":330.5},"parent_chunk_id":"c_tbl_0003_hdr","previous_chunk_id":"c_tbl_0003_r_001","next_chunk_id":"c_tbl_0003_r_003","related_chunk_ids":["c_tbl_0003_note_1"],"needs_review":false,"review_reasons":[],"source_location":{"file_name":"정책자금_운용지침.pdf","document_id":"d_9f2c...e1","page_no":null,"page_range":[12,13],"bbox":{"page":13,"x0":72.0,"y0":300.1,"x1":523.0,"y1":330.5},"extract_method":"pdf_text","heading_path":["제3장","2절","지원 산업 목록","1. 사출·프레스산업"],"locator":"제3장 > 2절 > 지원 산업 목록 > 1. 사출·프레스산업","dpi":null,"asset_id":null,"char_range":null,"table_id":"tbl_0003","figure_id":null,"transform":null}}}
```

분할표 Record는 `page_no:null` + `page_range:[12,13]`이되 자기 행은 실제로 단일 페이지에 있으므로
`bbox.page=13`처럼 **한 페이지로 확정**된다(§11.2 validator가 `page_range[0] ≤ bbox.page ≤
page_range[1]` 불변식을 강제).

**embedding_text 파생 규칙**(항상 자연어 + 짧은 출처 꼬리표 `(출처: {file} {page_label}, {locator})`):

| content_type | embedding_text 구성 |
| --- | --- |
| text / warning / footnote / reference / table-note | content 본문 + 출처꼬리표 |
| list-item | (heading_path 마지막) + ": " + marker + text + 출처꼬리표 |
| table-row | `content.embedding_text`(규칙/LLM 생성) + 출처꼬리표. 컬럼 의미 포함 보장 |
| procedure-step | "단계 {n}: " + step_label + actions + (branches) + 출처꼬리표 |
| infographic | summary + reading + data_points 요약 + 출처꼬리표. ocr_text는 metadata에만 |
| screenshot | purpose + actions(verb/target/value) 요약 + 출처꼬리표. ocr_text는 metadata에만 |
| flowchart / graph | semantics/summary(자연어). mermaid는 metadata에 보관 |
| flowchart-edge | "{from_node} → {to_node}" + (condition) + relation + 출처꼬리표 |

**적재 규칙**: chunk_id는 upsert PK(재실행 동일 입력 → 동일 chunk_id → 멱등 upsert). 빈
embedding_text 청크는 적재하지 않고 manifest `review_required`에 기록. jsonl과 xml은 동일 chunk
집합에서 생성되어 chunk_id로 교차 복원된다.

### 12.3 manifest (stdout 1줄 JSON + manifest.json)

```json
{"@@MANIFEST@@":true,"status":"ok","document_id":"d_9f2c...e1","source_sha256":"9f2c...e1",
 "file_name":"input.pdf","pipeline_version":"1.0.0",
 "counts":{"chunks":482,"by_type":{"text":210,"table-row":190,"screenshot":12},"pages":34},
 "extract_methods":{"pdf_text":410,"ocr":40,"layout_analysis":32},
 "outputs":{"xml":"/abs/out/d_9f2c/chunks.xml","jsonl":"/abs/out/d_9f2c/chunks.jsonl",
            "manifest":"/abs/out/d_9f2c/manifest.json"},
 "review_required":{"count":7,"reasons":["low_confidence:5","table_fallback:2"],
                    "chunk_ids":["c_..","c_.."]},
 "vision_used":true,"offline":false,"provider":"openai","tesseract_version":"5.3.4",
 "timings_ms":{"extract":1200,"structure":300,"serialize":150,"total":1850},
 "warnings":["dangling_ref:별표 2"]}
```

manifest는 **고유 센티넬 프리픽스(`"@@MANIFEST@@":true`)**를 포함하고 stdout 마지막 1줄로 항상
기록하며 `--outdir/manifest.json`에도 이중화한다. 부분 실패도 `status:"ok"` + `review_required`로
보고(비차단). 치명 실패만 비-0 종료코드 + `status:"error"`. **Spring은 stdout 휴리스틱이 아니라
`manifest.json` 파일을 권위 소스로 사용**하는 것을 권장한다(§16.1). manifest에는 OCR/offline
경로 분리를 위해 `tesseract_version`, provider 종류를 기록한다(키 자체는 미기록).

### 12.4 모델 필드 ↔ XML 요소·속성 매핑 (Round-Trip 규칙)

`to_chunks_xml`(직렬화)과 역파싱(검증)이 동일 규칙을 쓰도록 모델 필드명 ↔ XML명을 고정한다.
이 표가 round-trip 모호성을 제거한다.

| 모델(§11.3) | XML 요소/속성 | 비고 |
| --- | --- | --- |
| `FlowchartEdgeContent.relation` | `<relation>` (자식) | 이전 `text`에서 개명 → 1:1 |
| `FlowchartEdgeContent.from_node/to_node/condition` | `<flowchart-edge from/to/condition>` (속성) | |
| `FlowchartNodeContent.node_id/node_type` | `<flowchart node-id/node-type>` (속성) | |
| `FlowchartNodeContent.label/semantics` | `<label>`/`<semantics>` (자식) | |
| `GraphContent.notation/mermaid/summary` | `<graph notation>` + `<mermaid>`/`<summary>` | |
| `ProcedureStepContent.step_no/step_label` | `<procedure-step step-no/step-label>` (속성) | |
| `ProcedureStepContent.actions[]/detail/ocr_text` | `<action>`/`<detail>`/`<ocr-text>` (자식) | actions는 0..N |
| `Branch.on/target_step_id` | `<branch on/target-step-id>` (속성) | |
| `ScreenshotContent.screen_name/purpose` | `<screenshot screen-name>` + `<purpose>` | |
| `Action.verb/target/value/state` | `<action verb/target/value/state>` (속성) | |
| `Emphasis.target/meaning` | `<emphasis target>`(속성) + 텍스트=meaning | |
| `InfographicContent.info_kind/summary/reading` | `<infographic kind>` + `<summary>`/`<reading>` | |
| `DataPoint.name/value` | `<data-point name>`(속성) + 텍스트=value | 0..N |
| `Col.name/value` | `<col name>`(속성) + 텍스트=value | |
| `Meta.needs_review/review_reasons` | `<needs_review>`/`<review_reasons>` | jsonl metadata에도 |
| `SourceLocation.locator` | `<source_location locator>` (속성) | heading_path 평탄화 |

> XML 속성명은 케밥케이스(`node-id`, `step-no`), 모델 필드는 스네이크케이스(`node_id`,
> `step_no`)로 1:1 변환한다. 텍스트 노드 매핑(예: `<col>`/`<data-point>`/`<emphasis>`의
> textContent ↔ `value`/`meaning`)도 위 표로 고정해 직렬화·역파싱이 대칭이 된다.

---

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
