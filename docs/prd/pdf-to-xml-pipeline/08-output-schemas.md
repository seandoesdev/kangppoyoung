# 산출물 스키마 (Output Schemas) — PDF → RAG Chunk 파이프라인

> [공통 기반](00-foundation.md)에서 분량 분리. 산출물(XML 정본 / JSONL / manifest)과
> 모델 ↔ XML Round-Trip 매핑의 상세 스키마. 필요할 때만 참고한다.

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
