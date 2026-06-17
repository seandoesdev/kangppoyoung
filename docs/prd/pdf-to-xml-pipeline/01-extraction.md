# Step 1 · 추출 (Extraction) — PDF → RAG Chunk 파이프라인

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §5 · 선행 참조: 00-foundation
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 5. 추출 단계 (Extraction)

### 5.0 입력 사전 가드 (Input Pre-Guard)

악성·대용량 PDF의 DoS 표면을 **문서를 본격 처리하기 전에** 차단한다. Spring의 multipart 50MB
캡은 업로드 경로 전용이라 `ProcessBuilder`가 디스크 절대경로를 직접 받는 호출은 우회되므로,
**Python 계약 자체에 바이트·페이지·픽셀 상한**을 둔다.

1. **파일 바이트 상한**: `max_input_mb`(기본 100MB) 초과면 `doc` open 전에 즉시 종료코드 3.
   Spring도 `ProcessBuilder` 호출 직전 디스크 PDF 바이트를 재확인한다(이중 방어).
2. **페이지 수 상한**: `fitz.open()` 직후 `doc.page_count > max_pages`(기본 300)면 페이지 순회
   전에 종료코드 5(page-bomb 차단; "열고 난 뒤" 검사보다 이르게).
3. **픽셀폭탄 가드**: 각 렌더(`get_pixmap`) **전에** `예상 픽셀수 = clip_width_pt * clip_height_pt
   * (dpi/72)^2`를 계산해 `max_render_megapixels`(기본 40MP) 초과면 dpi를 강등하거나 해당 영역을
   skip+review. `colorspace=GRAY`·`alpha=False`로 Pixmap 바이트를 축소한다.
4. **동시 렌더 1개 제한**: 단일 프로세스 내 렌더는 직렬화해 메모리 스파이크를 억제한다.
5. **암호화/손상/0페이지**: open 실패·암호화·0페이지는 종료코드 3(InputError).

> 상한은 합리적 디폴트이며 `config`로 조정한다. `max_pages`는 open 직후 `page_count`로 선검사해
> 순회 비용 발생 전에 거부한다. 압축폭탄·거대 MediaBox는 (1)(2)(3)의 조합으로 1차 방어한다.

### 5.1 라이브러리 선택

| 용도 | 라이브러리 | 핵심 근거 |
| --- | --- | --- |
| PDF 텍스트+글리프 좌표+렌더+객체목록 | **PyMuPDF (fitz) ≥1.24** | `get_text("rawdict")`(글리프 char/bbox/font/**flags=폰트 속성 비트필드**), `get_text("words")`, `get_images`/`get_image_rects(xref)`/`get_drawings`, `get_pixmap(dpi=,clip=)`를 모두 동일 **top-left point 좌표계**로 제공. 판정·라우팅·OCR clip 렌더를 한 좌표계에서 일관 처리. |
| 표 셀/행/열 격자 복원 | **pdfplumber ≥0.11** | `find_tables`/`extract_tables`가 선·정렬 기반으로 셀 bbox와 행/열 격자를 복원. `Table.cells`(셀 bbox 리스트)로 병합 구조를 **복원·추정**한다(§7.0). 표 붕괴 여부(셀 수, 빈셀 비율, 행별 열수 불균일)를 객관 판정. |
| OCR (스캔/깨짐/표붕괴 영역 한정) | **pytesseract + Pillow** (+ Tesseract 5.x kor·eng) | `image_to_data(output_type=DICT)`로 단어별 text/conf/bbox(픽셀). conf를 meta에, 픽셀 bbox를 dpi로 역산해 point bbox 환원. 오프라인·무료. |
| 비텍스트 의미화 | **Vision LLM provider 추상화** (OpenAI gpt-4o 기본, +offline 폴백) | 인포그래픽/스크린샷/순서도는 단순 OCR 불가 → Vision 필요. 키 없으면 결정적 offline 폴백으로 완주. |
| XML 직렬화 | **lxml ≥5** | `el.text=value` 자동 이스케이프로 `<`/`>`/`&`/`"` 인젝션·깨짐 방지. `pretty_print`. |
| 데이터 모델·검증·JSON | **pydantic v2** | Meta·Content·BBox·SourceLocation 타입 강제. `model_dump(mode="json")`로 손실 없는 JSONL. enum으로 잘못된 값 차단. 스키마가 곧 계약. |
| CLI 진입점 | **argparse** (표준) | 무의존으로 `--pdf/--out/...` 계약 정의. stdout JSON·종료코드 규약 안정화. |

> **PyMuPDF 라이선스 — P0 결정 사항.** PyMuPDF는 AGPL/상용 듀얼 라이선스다. 정책자금 플랫폼이
> 상용/내부망 배포면 런타임 링크 시 AGPL 의무(소스 공개)가 트리거될 수 있으며 `extract_router`
> 뒤 격리만으로는 회피가 보장되지 않는다. **(A) 상용 라이선스 구매** 또는 **(B) `pypdfium2`(BSD)
> + pdfplumber 백엔드로 교체** 중 하나를 P0에서 결정하고, 추출 구현을 `extract_router` 뒤로
> 격리해 백엔드 교체를 가능하게 한다.

### 5.2 좌표계 모델 (Coordinate Model)

정본 좌표계는 **PDF 사용자 공간 point(1pt=1/72inch), 원점=페이지 좌상단(top-left)**, x→오른쪽·
y→아래 증가하는 PyMuPDF(`fitz.Rect`) 좌표다. (PDF 표준의 좌하단 원점이 아니라 top-left
정규화를 채택 — 이미지 픽셀과 직관 일치.)

- **page_no**: 1-based(PDF 표시와 일치). 0-based 내부 인덱스는 비노출.
- **bbox**: `[x0,y0,x1,y1] = (left,top,right,bottom)`, 단위 point. meta에 page_no와 항상 동반
  (bbox만으로는 페이지 미확정).
- **회전**: `page.rotation≠0`이면 PyMuPDF 정규화 좌표를 쓰고, 정규화 행렬을
  `source_location.transform`에 기록해 역복원.
- **OCR 픽셀→point**: `pt = px * 72 / dpi`(dpi=300이면 px*0.24). clip 렌더는 clip 원점
  오프셋을 더해 페이지 절대 point로 복원.
- **page_range**: 분할표·다중페이지 논리 병합 청크는 `page_range=[first,last]`. 단일 페이지는
  `[n,n]`로 정규화(둘 다 meta 보유).
- **pdfplumber 좌표 어댑터**: pdfplumber는 `top/bottom`(top-left 기준)과 `y0/y1`(bottom-left
  기준)을 동시에 노출하고 CropBox 오프셋·rotation 처리가 PyMuPDF와 미세하게 다르다. 따라서
  **"직접 호환"이라 가정하지 않고**, pdfplumber 좌표는 어댑터에서 `page.height`·CropBox 오프셋을
  반영해 **top-left point 단일 채널로만** 환산해 사용한다(`top/bottom`만 사용, `y0/y1`은 미사용).

> **좌표계 불일치 위험.** PyMuPDF(top-left) vs pdfplumber(top/bottom·y0/y1 병존) vs OCR 픽셀이
> 섞인다. 본 설계는 어댑터에서 top-left point 단일 채널로 강제하므로, 외부(예: 기존 PDFBox)
> bottom-left bbox와 비교·병합할 때는 y축 반전 변환을 반드시 적용한다. **CropBox 비-0 오프셋·
> rotation 케이스의 환산 테스트를 골든에 추가한다.** 회전 페이지의 transform 누락 시 bbox가
> 틀어진다.

### 5.3 텍스트 레이어 판정 (Detection)

페이지 단위 + 영역 단위 **2단계** 판정. 입력은 `get_text("rawdict")`와 `"words"`다.

> **`flags`는 글자 검증 신호가 아니다.** PyMuPDF span의 `flags`는 폰트 속성 비트필드
> (superscript/italic/serif/bold/mono)로, "정상 글리프 비율"을 직접 주지 않는다. 따라서 깨짐
> 감지는 **추출 시 `TEXT_CID_FOR_UNKNOWN_UNICODE` 플래그를 켜고 산출되는 `(cid:N)` 토큰 비율 +
> `U+FFFD`(치환 문자) 비율**로 정의한다. 즉 "정상 글리프 비율"이라는 직접 측정 불가 지표 대신
> **"유니코드 복원 실패 토큰 비율"**로 환원한다.

**페이지 단위 신호** → `PageDiagnosis`:

| 신호 | 산출 방식(PyMuPDF) | 깨짐/스캔 판정 |
| --- | --- | --- |
| `char_count` | 공백 제외 추출 문자수 | 0이면 텍스트 레이어 없음(스캔본 후보) |
| `cid_fallback_ratio` | `TEXT_CID_FOR_UNKNOWN_UNICODE` 추출 결과의 `(cid:N)` 토큰 / 전체 토큰 | >0.1 → 깨짐(CID-only/서브셋 폰트 ToUnicode 누락) |
| `replacement_ratio` | `U+FFFD` 문자수 / 전체 문자수 | >0.02 → 깨짐 |
| `glyph_recovery` | `1 − (cid_fallback_ratio + replacement_ratio)` 로 **환원 정의** | <0.85 → 깨짐(복원 실패 과다) |
| `hangul_ratio` | 한글음절+자모+CJK+ASCII / 전체 | <0.5 & 기호 과다 → 모지바케 |
| `image_area_ratio` | 이미지/래스터 bbox 합 / 페이지 면적 | >0.6 & char 적음 → 스캔본/이미지 전용 |

`glyph_recovery`는 별도 측정값이 아니라 위 두 실패 토큰 비율의 함수다(`flags` 미사용). 페이지
`verdict = ok_text | broken | scanned`. 우선순위 **scanned > broken > ok_text**.

**영역 단위 신호**: ok_text 페이지여도 표는 pdfplumber 격자 무결성으로, 그림/도식은 이미지/벡터
클러스터 내부 텍스트 부족으로 별도 판정·분리한다(§5.5).

**confidence**: ok_text=`glyph_recovery`(0.85~1.0 정규화), ocr=pytesseract 단어 conf 평균/100,
layout_analysis=provider self-report 또는 폴백 0.5 고정. `meta.confidence`에 [0,1] 기록.

> 임계값(0.85·0.1·0.02 등)은 한국 규정 PDF 표본 없이 정한 합리적 디폴트다. 산출 신호의 코드
> 레벨 경로는 위 표로 고정했으나 임계는 표본 코퍼스로 보정한다. 모지바케/CID-only 폰트에서
> 오판(정상→broken, broken→정상) 가능 → 경계 케이스는 `review_required`로 사람 검토에 노출한다.

### 5.4 라우팅 (Routing)

`extract_method ∈ {pdf_text, ocr, layout_analysis}`를 페이지 단위로 1차 결정하고 영역 단위로
override한다. **렌더(`get_pixmap`)는 OCR/layout이 실제 필요한 페이지·영역에서만 호출**한다(픽셀
가드 §5.0 적용).

**페이지 1차**

| verdict | 페이지 method | 근거(SPEC) |
| --- | --- | --- |
| ok_text | pdf_text (일부 영역만 ocr/layout 승격) | 텍스트 우선 |
| broken | ocr (텍스트 레이어 불신) | ② 추출 깨짐 |
| scanned | ocr; 도식 위주면 layout_analysis | ① 스캔본 |

**영역 override (ok_text/ocr 페이지 내부)**

1. **표**: pdfplumber 격자 무결(셀≥4, 빈셀<0.4, 행별 열수 일치율>0.8, 헤더 식별) → 그 영역만
   pdf_text; 붕괴(셀 검출 실패/열수 불균일/병합 과다) → 표 bbox만 clip 렌더 후 ocr(가능하면
   row-clip으로 격자 재구성), 사실상 이미지면 layout_analysis. (SPEC ③ 표 붕괴.)
2. **그림/도식/인포그래픽**: 이미지/벡터 클러스터 bbox 중 내부 텍스트 적은 영역 →
   layout_analysis. (SPEC ④.)
3. **스크린샷/순서도**: 동일 클러스터, `content_type`을 screenshot/flowchart로 분기,
   layout_analysis. 순서도는 노드/엣지 관계를 Mermaid로 산출.
4. **본문 문단·목록**: 항상 pdf_text(broken 페이지면 ocr).

**기록·결정성**: 각 Chunk `meta.extract_method`에 실제 방식 기록. 한 페이지가 영역별로
pdf_text/ocr/layout 혼합 가능(페이지 단일 값 강제 안 함). pdf_text는 완전 결정, ocr은 **환경
고정 시 재현적**(§13.2), 폴백 layout은 결정적. Vision LLM 경로만 비결정 → 해당 청크에 review
신호 + 멱등 캐시 키=`(sourceSha256, page, region_bbox, method)`.

### 5.5 영역 분리 (Region-Level Routing)

한 페이지를 region으로 분할해 텍스트 영역은 pdf_text, 표/그림 영역만 OCR/layout으로 보낸다.

1. **객체 인벤토리**:
   - 텍스트: `get_text("rawdict")` blocks(텍스트 bbox).
   - 래스터: `get_images(full=True)`로 xref 목록을 얻고 **각 xref마다** `get_image_rects(xref)`를
     호출해 페이지 내 출현 bbox를 수집한다 — 의사코드:
     `for img in page.get_images(full=True): for r in page.get_image_rects(img[0]): collect(r)`.
     인라인 이미지는 `get_image_rects`로 안 잡힐 수 있으므로 `rawdict`의 image 블록도 **병행
     수집**한다.
   - 벡터: `get_drawings()`(path→클러스터링).
   - 표: pdfplumber `find_tables()`(표 bbox+격자).
2. **분류**: table region(격자 무결성으로 method 결정) / figure region(이미지·벡터 클러스터 중
   내부 텍스트 부족 → layout) / text region(나머지 → pdf_text).
3. **겹침 해소**: 우선순위 **table > figure > text**. 표 bbox 내부 텍스트 블록은 표로 흡수(중복
   방지). 캡션·표주석은 별도 청크로 만들되 `related_chunk_ids`로 연결.
4. **읽기 순서**: 컬럼 추정 후 top→bottom, 다단이면 left-col→right-col 정렬로 previous/next 부여
   (순서 복원).

### 5.6 OCR 접근 (OCR Approach)

- **엔진/언어**: Tesseract 5.x, `lang="kor+eng"`. `image_to_data(output_type=Output.DICT)`로
  단어별 text/conf/bbox.
- **DPI**: 영역 clip 렌더 **300dpi 권장**(한글 인식률↔속도 균형). 표/세밀 영역은 설정으로
  400까지 상향(픽셀 가드 §5.0 적용). 렌더 PNG는 AssetStorage 규약대로 sha256 저장해 `asset_id`
  확보.
- **PSM**: 본문 블록 `--psm 6`, 페이지 전체 스캔본 `--psm 3`, 표 영역 clip `--psm 6`, 행 단위
  clip `--psm 7`. `--oem 1`(LSTM). 예: `--oem 1 --psm 6 -l kor+eng`.
- **전처리**(Pillow): grayscale → 적응 이진화(Otsu/Sauvola) → deskew(스캔본 기울기 보정) →
  소형 글자 2x 업스케일. 한글 자모 손상 방지를 위해 노이즈 제거는 보수적. 파라미터 고정으로 재현.
- **품질 게이트**: 단어 평균 conf<0.45 또는 한글 비율 비정상이면 그 영역을 layout_analysis로
  재시도 + `meta.needs_review`. Tesseract 미설치 시 ocr 경로는 명확 에러코드 실패(종료코드 6)
  또는 설정에 따라 layout_analysis 폴백/skip+review(비중단). `pytesseract.tesseract_cmd`는 설정값
  주입.
- **환경 기록**: OCR/offline-OCR 청크는 `manifest`에 `tesseract_version`을 기록한다(§13.2 회귀
  분리용). tesseract조차 없고 키도 없으면 비텍스트 영역은 PNG 자산만 남아 의미가 0이므로
  `needs_review=true`로 명시 격리한다(검색 가치 한계 인지).

### 5.7 핵심 시그니처

```python
def diagnose_page(page: "fitz.Page") -> PageDiagnosis: ...          # 텍스트 레이어 판정 휴리스틱
def route_page(page, diag: PageDiagnosis, pdfplumber_page) -> list[Region]: ...  # 페이지+영역 라우팅
def extract_text_region(page, region: Region, ctx: "DocContext") -> list[Chunk]: ...  # pdf_text 본문/목록
def render_region_png(page, bbox: BBox, dpi: int = 300) -> bytes: ...  # get_pixmap(clip=), 픽셀 가드 적용, OCR/Vision 대상만
def ocr_region(page, region: Region, assets: "AssetStore", dpi: int = 300,
               lang: str = "kor+eng") -> "OcrResult": ...           # clip 렌더 + image_to_data + 픽셀→point
```

---
