# PDF → RAG Chunk 변환 파이프라인

정책자금 규정·공고 PDF를 **RAG에 최적화된 `<chunk>` 기반 구조화 문서**로 변환한다.
모든 데이터는 `<chunk>`(= `<meta>` 구조·출처·관계 + `<content>` 의미)로 분할되고,
**원본 정본(`chunks.xml`)** 과 **검색용(`chunks.jsonl`)** 을 분리 산출한다.

> 설계·계약: [`docs/prd/PRD.md`](../docs/prd/PRD.md) §8 (파이프라인 요구사항 & 핵심 계약 —
> CLI·종료코드·ProcessBuilder·chunks.xml/jsonl/manifest 스키마·결정론적 chunk_id)
> 나중에 Spring 백엔드가 `ProcessBuilder`로 이 파이프라인을 스크립트 실행해 호출한다.

## 설치

```bash
python -m pip install -r pipeline/requirements.txt   # pdfplumber, pydantic, lxml
```

Python 3.10+ 필요. Vision(이미지 의미화)·OCR은 **선택**이며 미설치 시 offline 폴백으로 동작한다
(이미지 청크는 `needs_review`로 격리). 실제 의미화를 켜려면 `openai`(+`OPENAI_API_KEY`),
`pytesseract`(+ 시스템 `tesseract-ocr`, `tesseract-ocr-kor`)를 추가한다.

## 실행 (CLI)

```bash
python -m pipeline --input "source/문서.pdf" --outdir "out/문서"
```

| 옵션 | 기본 | 설명 |
| --- | --- | --- |
| `--input` | (필수) | 입력 PDF 경로 |
| `--outdir` | (필수) | 산출물 디렉터리 |
| `--doc-id` | PDF 해시 | 문서 ID 지정 |
| `--confidence-threshold` | 0.7 | 미만이면 `needs_review(low_confidence)` |
| `--table-confidence-threshold` | 0.6 | 미만이면 표 구조화 약화 |
| `--max-chunk-chars` | 800 | 일반 본문 청크 상한 |
| `--no-verify` | — | 검증 단계 생략 |

**산출물** (`<outdir>/`): `chunks.xml`(정본) · `chunks.jsonl`(벡터DB 적재) · `manifest.json`(집계·검증).
stdout 마지막 줄은 `{"@@MANIFEST@@":true, ...}` 1줄(JSON).

**종료코드**: 0 성공(부분성공 포함) · 2 인자오류 · 3 입력오류 · 4 검증실패(round-trip/parity) · 5 한도초과 · 1 내부오류.

## 실행 (Docker — backend 동거, 토폴로지 A)

운영에서는 **backend(Spring) 이미지에 Python 파이프라인을 함께 실어**(설계 §16.6 A),
Spring 이 **동일 컨테이너에서 `ProcessBuilder` 로 `python -m pipeline` 을 호출**한다.
별도 파이프라인 컨테이너는 없다. 이미지 = `eclipse-temurin:25-jre` + `python3` +
`tesseract-ocr`/`tesseract-ocr-kor` + 격리 venv(`/opt/pipeline-venv`) + `/app/pipeline/` 패키지.

빌드는 저장소 루트를 컨텍스트로 한다:

```bash
docker compose build backend     # backend.build.context = . (루트), dockerfile = backend/Dockerfile
docker compose up -d
```

Spring 이 쓸 인터프리터는 환경변수 `PIPELINE_PYTHON=/opt/pipeline-venv/bin/python` 로 노출되며,
작업디렉터리 `/app` 에서 `python -m pipeline` 가 해석된다(§16.4 계약). 수동 검증:

```bash
docker compose exec backend /opt/pipeline-venv/bin/python -m pipeline \
  --input /app/<문서>.pdf --outdir /app/out/<id>
```

한글 파일명은 컨테이너 안 UTF-8(`PYTHONUTF8=1`)로 안전하다. `OPENAI_API_KEY` 는 env 로만 주입
(없으면 offline 폴백). 종료코드·`manifest.json` 규약은 CLI 와 동일하다.

> 로컬 개발(Docker 없이)은 위 [실행 (CLI)](#실행-cli) 의 venv 방식을 그대로 쓴다.

## Spring 연동 (참고)

Spring은 stdout 휴리스틱이 아니라 **`manifest.json` 파일을 권위 소스**로 쓰고, **종료코드로 분기**한다.
비밀키(`OPENAI_API_KEY`)는 **env로만** 전달(인자 금지). stdout은 파일로 리다이렉트하거나 비동기로
펌프해 `waitFor` 데드락을 피한다. 자세한 계약은 설계 §16.

## 산출물 구조 (예)

```xml
<chunk id="c_4a38c679...">
  <meta>
    <content_type>table-row</content_type>
    <page_no>2</page_no>
    <heading_path><h>혁신성장 분야</h></heading_path>
    <table_id>tbl_8e7564e4</table_id>
    <bbox page="2" x0="135.9" y0="230.3" x1="439.6" y1="260.7"/>
    <previous_chunk_id>...</previous_chunk_id><next_chunk_id>...</next_chunk_id>
    <source_location locator="혁신성장 분야"/>
  </meta>
  <content>
    <table-row>
      <col name="분야">제조공정</col>
      <col name="품목">3D머신비전</col>
      <embedding_text>...컬럼 의미 포함 검색 문장...</embedding_text>
    </table-row>
  </content>
</chunk>
```

`chunks.jsonl` 한 줄 = `{chunk_id, document_id, content_type, embedding_text, metadata}`(Meta 전체 평탄 dump).

## 검증 (원본 ↔ 변환 정확성)

CLI는 변환 직후 자동 검증하고 결과를 `manifest.verification`에 기록한다.

- **text_coverage(char_recall)** — 원문 글자 다중집합 보존율(토큰화·재정렬 불변). 게이트 ≥ 0.99.
- **xml_roundtrip** — `chunks.xml` 역파싱이 모델·텍스트와 동치.
- **xml_jsonl_parity** — XML chunk_id == JSONL(+skipped) 1:1.
- **relations_intact** — parent/prev/next/related 참조에 dangling 없음.
- **chunk_id_unique** — 결정적 ID 유일·멱등(동일 PDF → 동일 ID).

`source/` 3개 문서 실측: char_recall **0.9984 / 0.9999 / 1.0000**, 모든 검사 통과.

## offline 한계

`tesseract`·`OPENAI_API_KEY`가 없으면 이미지에 박힌 텍스트(스캔·인포그래픽)는 추출하지 못하고
`infographic` 청크 + `needs_review(offline_fallback)`로 격리한다. 텍스트 레이어는 100% 가까이 보존된다.
(PDF 3은 그래픽 위주 브로슈어라 이미지 14개가 검토 대상으로 표시됨.)
