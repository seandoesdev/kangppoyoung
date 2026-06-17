# 정책자금 지원 업무 플랫폼

PDF → RAG 변환 파이프라인 · Spring 백엔드 · React 프론트엔드로 구성된다.

## 사용 방법

### 1. PDF → RAG Chunk 파이프라인 (`pipeline/`)

PDF를 검색·추론에 최적화된 `<chunk>` 기반 구조화 문서(XML 정본 + JSONL)로 변환한다.

```bash
# 설치 (Python 3.10+)
python -m pip install -r pipeline/requirements.txt

# 실행: source/ 의 PDF를 변환 → out/ 에 산출
python -m pipeline --input "source/문서.pdf" --outdir "out/문서"
```

산출물(`<outdir>/`): `chunks.xml`(원본 정본) · `chunks.jsonl`(벡터DB 적재용) · `manifest.json`(집계·검증).
변환 직후 텍스트 보존율·round-trip·관계 무결성을 자동 검증한다. 옵션은 [`pipeline/README.md`](pipeline/README.md) 참조.

### 2. 백엔드 (`backend/`, Spring Boot)

```bash
# 단독 실행
cd backend && ./gradlew bootRun

# 또는 전체 스택(nginx + backend + mysql)
docker compose up --build
```

### 3. 프론트엔드 (`frontend/`, React + Vite)

```bash
cd frontend
npm install
npm run dev        # 개발 서버
```

## 문서

- 제품 요구사항: [`docs/prd/PRD.md`](docs/prd/PRD.md) · [`docs/prd/BACKEND_PRD.md`](docs/prd/BACKEND_PRD.md)
- 파이프라인 설계: [`docs/prd/pdf-to-xml-pipeline.md`](docs/prd/pdf-to-xml-pipeline.md) (+ 단계별 세부 `docs/prd/pdf-to-xml-pipeline/`)
- API 계약: [`docs/api/openapi.yaml`](docs/api/openapi.yaml)
