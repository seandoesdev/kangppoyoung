# Step 3 · 표 처리 (Table Processing) — PDF → RAG Chunk 파이프라인

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §7 · 선행 참조: 00-foundation, 01-extraction
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 7. 표 처리 (Table Processing)

표는 SPEC의 핵심 요구사항이다. **표 전체를 한 Chunk로 저장 금지**, 각 Row를 독립 `table-row`
청크로 정규화한다.

> **병합셀 메타는 입력이 아니라 파생값이다(핵심 정정).** pdfplumber `find_tables`/
> `extract_tables`는 병합셀을 "좌상단 셀에 텍스트, 나머지는 `None`"으로 반환할 뿐 셀 단위
> `rowspan/colspan/is_origin`을 노출하지 않는다(공식 동작). PyMuPDF `find_tables`도 마찬가지로
> cell `None` 패턴만 준다. 따라서 본 파이프라인은 **span 메타를 입력으로 받지 않고 §7.0에서
> 직접 복원·계산**한다. `colspan`/`rowspan`/`is_origin`은 모두 파이프라인이 산출하는 파생값이다.

### 7.0 병합 구조 복원 (RECOVER_SPANS — span 파생)

`RESOLVE_SPANS`(§7.2) **이전에** pdfplumber `Table.cells`(셀 bbox 리스트)와 행·열 격자선(또는
`extract_tables`의 `None` 패턴)으로 병합 구조를 추정한다.

```
RECOVER_SPANS(table):
  cells      = table.cells                 # 각 셀의 (x0, top, x1, bottom)
  col_edges  = canonical_x_edges(cells)    # 정렬·라운딩된 열 경계
  row_edges  = canonical_y_edges(cells)    # 정렬·라운딩된 행 경계
  grid       = empty_grid(len(row_edges)-1, len(col_edges)-1)
  for cell in cells:
    r0,r1 = index_span(cell.top, cell.bottom, row_edges)   # 셀 높이가 몇 개 행을 덮는가
    c0,c1 = index_span(cell.x0,  cell.x1,     col_edges)   # 셀 폭이 몇 개 열을 덮는가
    rowspan = max(1, r1-r0); colspan = max(1, c1-c0)
    grid[r0][c0] = CellBox(text=cell.text, rowspan=rowspan, colspan=colspan,
                           is_origin=True, is_empty=(cell.text.strip()==""))
    mark_covered(grid, r0,c0, rowspan, colspan)            # 덮인 좌표는 origin 참조만
  return grid
```

- **격자선 우선**: lattice(괘선) 표는 명시 수직/수평선 교차점으로 셀 사각형을 만들고, 셀 폭/높이를
  **최소 셀 단위**(col_edges/row_edges 간격)와 비교해 span을 추정한다.
- **무괘선 폴백**: 괘선이 없으면 `extract_tables`의 `None` 패턴(병합 셀의 덮인 칸은 `None`)으로
  rowspan/colspan을 역추정한다.
- 즉 입력 `raw_grid[r][c] = CellBox{text, x0,x1,top,bottom, page_no, colspan, rowspan,
  is_origin, is_empty}`의 `colspan/rowspan/is_origin`은 **본 단계가 복원한 값**이다.

### 7.1 탐지·격자 복원

추출경로는 텍스트 레이어 우선(스캔/깨짐만 OCR). 표 영역은 pdfplumber `find_tables()`를 두 전략
으로 실행한다.

- **lattice(선 기반)**: `page.lines`(드로잉 선)에서 vertical/horizontal explicit_lines 추출.
  명시 괘선이 충분하면 가장 정확. 수직선×수평선 교차점으로 cell 사각형 → §7.0이 셀 폭/높이로
  rowspan/colspan을 추정.
- **stream(좌표 기반/무괘선)**: 선이 없으면 글자 x/y 좌표 클러스터로 행·열 추정. 헤더 행의 x
  경계를 **열 앵커**로 고정하고 본문 행을 가장 가까운 앵커에 스냅.

`table_settings`(`vertical_strategy`, `horizontal_strategy`, `snap_tolerance`, `join_tolerance`,
`intersection_tolerance`)를 튜닝하고, 두 전략 중 셀 채움률·열수 일관성이 높은 쪽을 채택한다.

**tableConfidence** = w1·열수일관성 + w2·(1−과도빈칸비율) + w3·격자정합도 + w4·(1−스냅이탈률).
임계(0.7) 미만이면 구조화 포기 → 표 영역 PNG 렌더 → `figure`/`table-note` 청크 fallback(추출
평문은 검색용 보조 content로 보존, 누락 방지).

### 7.2 정규화 알고리즘

```
NORMALIZE_TABLE(table):
  grid       = RECOVER_SPANS(table)                    # §7.0: 셀 bbox→격자→span 복원(파생)
  grid       = RESOLVE_SPANS(grid)                     # rowspan/colspan materialize
  headerRows = DETECT_HEADER_ROWS(grid)
  col_names  = FLATTEN_MULTIHEADER(grid, headerRows)   # 부모_자식 결합
  data       = grid[after headerRows]
  FILL_DOWN(data, fill_cols=detect_key_cols(col_names))   # 세로병합 상속
  data       = APPLY_SECTION_INHERITANCE(data)         # 섹션행 → row.section
  return Table(col_names, data, headerRows)
```

**RESOLVE_SPANS — 병합셀 반복 채움**: §7.0이 복원한 rowspan=R, colspan=C 셀의 원본 값을 덮인
모든 `(r..r+R-1, c..c+C-1)` 좌표에 동일 값으로 복제(materialize). origin 좌표만 `is_origin=true`
표시(중복 임베딩텍스트 방지).

**FILL_DOWN — 세로 병합(계층 키) 상속**: 위 행 값이 아래 행들에 적용되는 좌측 키/계층열만
`fill_cols`에 포함한다.

```
FILL_DOWN(data, fill_cols):
  for c in fill_cols:
    last = None
    for r in data_rows(top→bottom):
      if data[r][c].empty and has_span_inherit(r,c): data[r][c].value = last; data[r][c].filled = True
      elif not data[r][c].empty: last = data[r][c].value
```

> 빈칸이 "병합 상속"인지 "진짜 빈값"인지 구분한다. §7.0이 복원한 span 메타가 있으면 상속,
> 없고 데이터열이면 빈값 유지(과채움 금지). 금액·수치 데이터열은 기본 제외한다. 결과: 모든
> 데이터 Row는 빈 상속칸이 없어 Record 하나만 떼어도 상위 분류·병합 키가 함께 들어가 의미가
> 완결된다.

### 7.3 다단 헤더 결합 (Multi-Header Flatten)

다단(2단 이상) 헤더를 **부모_자식 결합 컬럼명**으로 평탄화한다. 상단의 "데이터 아닌 라벨 행"
연속 구간을 `headerRows`로 식별(반복 라벨·colspan 병합 존재, 아래에 데이터행 시작).

```
FLATTEN_MULTIHEADER(grid, headerRows):
  for each data col k:
    path = [grid[hr][k].value for hr in headerRows if value and (path empty or value != path[-1])]
    name = '_'.join(clean(path))           # 예: ["사업정보","사업명"] → "사업정보_사업명"
    if name in used: name += '_' + str(dup_idx)
    col_names[k] = name
```

결합 규칙: 단일 헤더는 그대로, 빈 하위 셀은 부모만, 빈 부모는 자식만. 공백 trim·개행 제거·내부
공백 1칸. 결과 컬럼명(`사업정보_사업명`, `지원정보_지원금액` …)이 곧 `<col name="...">`의 name이
되어, 어느 그룹 소속인지가 컬럼명만으로 드러난다.

### 7.4 섹션 행 상속 (Section Inheritance)

표 내부 "섹션 행"(예 `1. 사출·프레스산업`)을 인식하고 다음 섹션 전까지 하위 Record에 상속한다.

```
IS_SECTION_ROW(row): (한 칸만 값 or colspan 전폭)
                     and 섹션 마커(^\d+[.)]\s | ^[가-힣]\.\s | ^[IVXivx]+\.\s | ^【.*】)
                     and 이어지는 행이 정상 데이터행
APPLY_SECTION_INHERITANCE(data):
  cur=None; path=[]; out=[]
  for row in data:
    if IS_SECTION_ROW(row): path = update_path(path, level_of(row), row.label); cur = row.label
                            emit_section_chunk(row)   # table-note 섹션 청크; continue
    if IS_TOTAL_ROW(row):   emit_total_chunk(row); continue   # 소계/합계는 상속 안 함
    row.section = cur; row.section_path = path[:]; out.append(row)
  return out
```

각 데이터 Record는 가상 컬럼 `<col name="섹션">사출·프레스산업</col>`을 부여받아 자립한다.
섹션행 자체도 하나의 청크(`content_type=table-note`)로 만들고, 하위 Record들의
`related_chunk_ids`에 섹션 청크를 연결한다. 섹션은 `heading_path`에도 반영한다.

### 7.5 페이지 넘김 병합 (Cross-Page Merge)

페이지 바뀜만으로 분리하지 않고 논리 병합한다.

```
IS_CONTINUATION(t1, t2):
  return same_colnames(t1,t2)              # 헤더 동일(또는 t2 무헤더 허용)
     and same_col_anchors(t1,t2,tol)       # 열 개수·열 앵커 x좌표 정렬
     and first_row_is_data(t2)             # t2 첫(헤더 제외) 행이 데이터(새 표제 아님)
MERGE_CROSS_PAGE(tables):
  merged=[]; i=0
  while i < len(tables):
    t = tables[i]
    while i+1 < len(tables) and IS_CONTINUATION(t, tables[i+1]):
      t = MERGE_TABLES(t, tables[i+1]); i += 1
    merged.append(t); i += 1
  return merged
```

`MERGE_TABLES`: t2의 반복 헤더행 제거(헤더 1벌 유지), 데이터행 append, **`page_range=[first_page,
last_page]`**(각 Record는 자기 행의 실제 page_no 보존). 3개 이상 페이지 연쇄 병합 시 `last`는
**마지막으로 흡수된 테이블의 페이지**이며 §5.2의 `[first,last]` 정규화와 일치한다(`[p,p+1]`처럼
중간 페이지를 누락하지 않는다). 세로 병합 fill-down·섹션 상속 상태를 **페이지 경계 너머로 계승**.
`table_id`는 단일 유지(논리 1표). 연쇄로 t3,t4도 반복.

### 7.6 Record → Chunk + embedding_text

```
ROW_TO_CHUNK(table, row, idx, ctx):
  cid  = make_chunk_id(...)               # §13.1 결정적 ID(가독 별칭 c_{table_id}_r_{idx})
  cols = [Col(name, row[name]) for name in table.col_names if present]
  if row.section: cols.append(Col('섹션', row.section))
  emb  = GEN_EMBEDDING_TEXT(row, table.col_names, row.section, table.caption)
  meta = build_meta(cid, ctx, page_no=row.page, page_range=table.page_range,
                    content_type='table-row', table_id=table.id,
                    heading_path=ctx.heading_path + [table.caption, row.section],
                    extract_method=row.method, confidence=row.conf, bbox=row.bbox,
                    parent_chunk_id=table.header_chunk_id,
                    related_chunk_ids=[table.caption_chunk_id, row.section_chunk_id])
  return Chunk(meta, Content(TableRow(cols, embedding_text=emb)))
```

**embedding_text 생성**(결정적 템플릿 1차, LLM은 선택적 보강):

```
GEN_EMBEDDING_TEXT(row, cols, section, caption):
  subj    = pick_subject(row)             # *명/명칭/품목 우선, 없으면 첫 데이터 열
  clauses = [f"{humanize(c)}{josa('은',c)} {v}" for c,v in row if c!=subj and v]
  text    = f"{subj}{josa('은',subj)} " + ', '.join(clauses) + '이다. '
  if section: text += f"{section} 분류에 속한다. "
  if caption: text += f"《{caption}》 표에 포함된다."
  return normalize_particles(text)        # 은/는·이/가·을/를 받침 보정(결정적)
```

예: `"자동차 부품 제조업은 산업분류코드 1234에 해당하며 제조업 대분류(사출·프레스산업)에
포함된다."` LLM 보강은 `temperature=0`으로 매끄러운 문장 생성하되, **모든 셀 값이 문장에
등장하는지 검증**(value-check) 통과 시에만 채택, 실패 시 템플릿 폴백. embedding_text는 content
안에 두어 답변 근거가 content에 존재하도록 보장한다. value-check는 인젝션(셀값에 숨긴 지시)
완전 차단이 아니므로, LLM 보강이 개입한 청크는 §21의 외부 데이터 마킹 대상이다.

### 7.7 표 처리 엣지 케이스

| 케이스 | 처리 |
| --- | --- |
| 병합 상속 빈칸 vs 진짜 빈값 | §7.0 복원 span 있으면 fill-down, 없고 데이터열이면 빈값 유지(`<col name=".." />`) |
| 소계/합계 행 | `소계·합계·계` 키워드+수치정렬로 식별, 별도 `table-note` 청크(섹션 상속 대상 아님) |
| 반복 헤더 오인 | `IS_CONTINUATION` 헤더 동일성 검사로 제거 후 1벌만 유지 |
| 섹션행 vs 다단헤더 | 섹션행='아래 데이터행 이어짐'+마커, 헤더='상단 연속 라벨행' |
| 셀 내 줄바꿈 | 개행을 공백으로 합쳐 단일 col 값. y버킷 `row_eps`를 글자높이 기반으로 두어 오분할 방지 |
| 무괘선 열 흔들림 | 헤더 x앵커에 본문 스냅. 스냅 이탈률 높으면 tableConfidence↓ → image fallback |
| rowspan 페이지 경계 | 이전 페이지 마지막 상속값을 다음 페이지 첫 행에 계승 |
| 중복 컬럼명 | `_2`,`_3` suffix로 유일화, 원 헤더 텍스트는 source_location에 보존 |
| 빈/단일행 표 | 헤더만이면 Record 0개+표 설명 청크만. 단일 행도 정상 1 Record |
| 셀 내 XML 특수문자 | lxml 자동 이스케이프 경로만(문자열 조립 금지), 제어문자 스트립 후 라운드트립 검증 |

---
