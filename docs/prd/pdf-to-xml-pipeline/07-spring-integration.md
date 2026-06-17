# Step 7 · Spring 연동 계약 (Spring ↔ Python Contract) — PDF → RAG Chunk 파이프라인

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §16 · 선행 참조: 00-foundation
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 16. Spring 연동 계약 (Spring ↔ Python Contract)

Spring이 `ProcessBuilder`로 실행하는 단일 진입점. **stdout = manifest(JSON 1줄) 전용**,
**stderr = 로그 전용**, 산출물은 파일로 기록. Java 내부 구현은 사용자가 본 계약에 맞춰 작성한다
(본 문서는 Java 코드를 정의하지 않으며, §16.4 스니펫은 계약을 설명하는 참조용이다).

### 16.1 CLI 계약 · stdout 규약

```python
def main() -> int: ...   # argparse 진입점, stdout JSON + exit code
```

```
python -m pipeline \
  --input  /abs/path/input.pdf \
  --outdir /abs/path/out/d_9f2c \
  [--doc-id d_9f2c...e1] \
  [--ocr-lang kor+eng] \
  [--confidence-threshold 0.6] \
  [--table-confidence-threshold 0.7] \
  [--max-chunk-chars 1200] \
  [--max-input-mb 100] [--max-pages 300] \
  [--vision (auto|on|off)] [--offline] \
  [--tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe"] \
  [--emit (xml|jsonl|both)] [--log-level info] [--timeout-sec 600]
```

| 인자 | 필수 | 기본 | 설명 |
| --- | --- | --- | --- |
| `--input` | 필수 | — | 입력 PDF 절대경로 |
| `--outdir` | 필수 | — | 산출물 디렉토리. `chunks.xml`/`chunks.jsonl`/`manifest.json` 기록 |
| `--doc-id` | 선택 | 파일해시 자동 | document_id 고정 주입(재색인 일관성) |
| `--ocr-lang` | 선택 | `kor+eng` | tesseract 언어팩 |
| `--confidence-threshold` | 선택 | `0.6` | 미만 청크 review_required 표시 |
| `--table-confidence-threshold` | 선택 | `0.7` | 미만 표는 image fallback |
| `--max-input-mb` | 선택 | `100` | 입력 PDF 바이트 상한(초과 종료코드 3) |
| `--max-pages` | 선택 | `300` | 페이지 수 상한(open 직후 검사, 초과 종료코드 5) |
| `--vision` | 선택 | `auto` | 비텍스트 의미화 LLM 사용 여부 |
| `--offline` | 선택 | off | API 키 없이 동작(폴백 설명문) |
| `--tesseract-cmd` | 선택 | PATH | tesseract 절대경로 주입 |
| `--timeout-sec` | 선택 | `600` | 자체 워치독(초과 시 부분 산출 + 종료코드 5) |

**stdout 규약(서드파티 오염 방어 포함)**: manifest JSON **외 어떤 것도 출력 금지**(파이프라인
코드는 print 금지, 모든 진단은 logging→stderr). 그러나 PyMuPDF/pdfplumber/openai/Pillow 등 **C
확장이 fd1(stdout)으로 경고를 흘릴 수 있으므로**, 진입 시 **OS 레벨로 C-stdout(fd 1)을 fd 2로 dup
리다이렉트**해 서드파티 stdout 누수를 stderr로 강제한다. 또한 manifest에 센티넬
프리픽스(`"@@MANIFEST@@":true`)를 붙인다. **권장: Spring은 stdout 파싱 대신 `manifest.json` 파일을
권위 소스로 읽는다**(파일 이중화가 이미 존재; stdout 휴리스틱 의존 제거).

**원자적 쓰기·동시 실행**: `chunks.xml`/`chunks.jsonl`은 temp 파일에 쓰고 `fsync` 후 같은 볼륨
내 **원자적 rename**으로 교체하며, `manifest.json`은 두 산출물 rename 성공 **후** 마지막에 쓴다
(중간 실패 시 잘린 jsonl을 Spring이 적재하는 위험 차단). 같은 doc-id로 동시 2회 실행은 `outdir`
lock 파일로 배제하거나 Spring이 doc-id 단위 작업 큐로 직렬화한다. 강제종료 시 부분 산출물은
`.partial` 접미사로 격리한다.

### 16.2 종료코드 (Spring 분기용)

| 코드 | 의미 | Spring HTTP | 재시도 |
| --- | --- | --- | --- |
| 0 | 성공 또는 부분성공(review_required 포함) | 200 (+review 게이트) | — |
| 2 | 인자/사용법 오류(argparse) | 400 | 무의미 |
| 3 | 입력 오류(파일 없음/PDF 아님/암호화/손상/0페이지/바이트 상한 초과) | 422 | 무의미 |
| 4 | 검증 실패(라운드트립/텍스트 보존/모델 round-trip 미달) | 500 | 무의미 |
| 5 | 타임아웃/리소스 한도 초과(페이지 상한·픽셀 가드 포함) | 504 | 가능 |
| 6 | 외부 의존성 오류(tesseract 미설치, LLM 불가 & not offline) | 500/설정 점검 | 설정 후 |
| 1 | 미분류 내부 오류 | 500 | 가능 |

### 16.3 오류 모델

예외 계층(`pipeline/errors.py`): `PipelineError(base, .exit_code, .category)` ←
`UsageError(2)` / `InputError(3)` / `ValidationError(4)` / `TimeoutError(5)` /
`DependencyError(6)` / `InternalError(1)`.

**부분 실패(비차단)** — 종료코드 0 유지, manifest 사유 기록: 청크 confidence<임계
(`low_confidence`), 표 fallback(`table_fallback`), Vision 실패 폴백(`vision_fallback`), 의미화
실패(`describe_failed`), dangling ref(`warnings`).

치명 실패(비-0) 시 stdout manifest:

```json
{"@@MANIFEST@@":true,"status":"error","exit_code":3,"category":"input",
 "message":"PDF is encrypted and cannot be opened",
 "document_id":null,"file_name":"input.pdf","pipeline_version":"1.0.0"}
```

메시지는 안전한 요약만(스택트레이스·LLM 원문·PII·`sk-` 패턴 미포함). 상세는 stderr 로그로만.
모든 예외는 top-level handler에서 catch → 분류·manifest 작성·종료코드 반환(uncaught로 죽지
않음). 부분 산출물은 가능하면 flush(원자적 쓰기로 부분성 격리).

### 16.4 Spring ProcessBuilder 호출 (참조 스니펫 · 계약 설명)

> 아래는 Java 측이 본 계약에 맞춰 구현해야 할 **참조 스니펫**이다(파이프라인 산출물이 아니라
> 계약 예시). 실제 Java 파일 수정은 사용자가 담당한다. **핵심: stdout을 동기 완독 후 waitFor를
> 부르면 데드락이 나므로(자식이 hang하면 readAllBytes가 EOF까지 영원히 블록되어 워치독이
> 무력화됨), stdout도 비동기 펌프하거나 파일로 리다이렉트한 뒤 `manifest.json`을 권위 소스로
> 삼아야 한다.**

```java
List<String> cmd = new ArrayList<>(List.of(
    pipelinePython,                         // venv 절대경로 권장: D:\...\.venv\Scripts\python.exe
    "-m", "pipeline",
    "--input",  inputPdf.toAbsolutePath().toString(),
    "--outdir", outDir.toAbsolutePath().toString(),
    "--doc-id", docId,
    "--ocr-lang", props.getOcrLang(),                                   // "kor+eng"
    "--confidence-threshold",       String.valueOf(props.getConfidenceThreshold()),
    "--table-confidence-threshold", String.valueOf(props.getTableConfidenceThreshold()),
    "--max-input-mb", String.valueOf(props.getMaxInputMb()),
    "--vision", props.isVisionEnabled() ? "auto" : "off",
    "--log-level", "info"));

String key = openAiKey;                       // @Value("${OPENAI_API_KEY:}")
if (key == null || key.isBlank()) cmd.add("--offline");   // 키 없으면 오프라인 폴백 강제

ProcessBuilder pb = new ProcessBuilder(cmd);
pb.directory(props.getPipelineWorkdir().toFile());        // 작업디렉토리 = pipeline 루트
Map<String,String> env = pb.environment();
if (key != null && !key.isBlank()) env.put("OPENAI_API_KEY", key);  // 비밀은 env로만(인자 금지)
env.put("OPENAI_MODEL", props.getVisionModel());          // gpt-4o
env.put("PYTHONUTF8", "1");                                // Windows 한글 깨짐 방지(필수)
env.put("PYTHONIOENCODING", "utf-8");
pb.redirectErrorStream(false);                            // stdout/stderr 분리(중요, merge 금지)
pb.redirectOutput(stdoutTmp.toFile());                    // stdout을 파일로(데드락 회피) — manifest.json을 권위로 사용

Process p = pb.start();
Thread errPump = consumeStderrAsync(p.getErrorStream(), log);   // stderr 비동기 흡수(sk- 마스킹 포함)
boolean done = p.waitFor(props.getTimeoutSec(), TimeUnit.SECONDS);  // stdout 동기 완독 없이 즉시 워치독
if (!done) {
    p.descendants().forEach(ProcessHandle::destroyForcibly);  // 자식 트리(손자 tesseract/소켓)까지 종료
    p.destroyForcibly(); errPump.join(2000);
    throw new PipelineTimeoutException();
}
errPump.join(2000);
int code = p.exitValue();

// 권위 소스 = manifest.json 파일(스니펫의 stdout 휴리스틱 비의존)
PipelineManifest m = objectMapper.readValue(outDir.resolve("manifest.json").toFile(), PipelineManifest.class);
switch (code) {
    case 0    -> { /* ok/partial: m.reviewRequired 를 승인 게이트로 */ }
    case 2, 3 -> throw new BadPdfException(m);             // 4xx
    case 4    -> throw new PipelineValidationException(m); // 500
    case 5    -> throw new PipelineTimeoutException();     // 504
    case 6    -> throw new PipelineDependencyException(m); // 설정 점검
    default   -> throw new PipelineInternalException(m);   // 500
}
// 후속: m.outputs.jsonl → Vector DB 적재 큐, m.outputs.xml → 정본 보관
```

**Java가 맞춰야 할 불변식**:

- **데드락 회피**: stdout을 `readAllBytes()`로 동기 완독한 뒤 `waitFor`를 부르면 자식 hang 시
  워치독이 무력화된다. stdout을 **파일로 리다이렉트**(위 스니펫)하거나 stderr처럼 **별도 스레드로
  비동기 펌프**한 뒤 `waitFor(timeout)`를 건다.
- **권위 소스 = manifest.json 파일**: stdout "마지막 비공백 줄" 휴리스틱은 서드파티 stdout 누수에
  취약하므로 파일을 우선한다(파이썬 측은 fd1→fd2 dup + 센티넬로 이중 방어, §16.1).
- **프로세스 트리 종료**: 타임아웃 시 `p.descendants()` 순회로 손자(tesseract/openai 소켓)까지
  강제 종료한다(Windows Job Object/`taskkill /T`, 리눅스 process group). 파이썬 워치독도
  `atexit/finally`에서 자식 tesseract subprocess를 명시 kill하고, 블로킹 C 소켓은 깨지 못하므로
  OpenAI 소켓 타임아웃(`llm_timeout_sec`)을 별도로 강제한다.
- **비밀은 env map으로만**(커맨드라인 인자 금지, 프로세스 목록 노출 방지); stderr 흡수 시 `sk-`
  패턴 마스킹 필터 적용.
- 작업디렉토리=pipeline 루트; 인코딩=`PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` + Java UTF-8 디코드
  (Windows CP949 회피); 산출물 위치는 `manifest.outputs` 경로를 신뢰(추측 금지).

### 16.5 asset 규약

렌더 PNG 자산은 Spring `AssetStorage` 규약과 동일하게 **sha256 hex(64 hex)**로 식별하며,
`source_location.asset_id`는 `/api/v1/notices/assets/{sha256}` 내부 참조를 가리킨다(외부 URL/
`data:` URI 금지).

### 16.6 배포 토폴로지 (Deployment Topology)

> **실행 모델 ↔ 배포 인프라 불일치 — 반드시 결정.** 본 설계의 로컬 실행 모델은 Windows 호스트
> venv(`D:\...\.venv\Scripts\python.exe`)에서 `ProcessBuilder`가 python을 부르는 형태지만, 운영
> backend는 `eclipse-temurin:25-jre` 단일 컨테이너로 빌드·배포되며 Python·PyMuPDF·pdfplumber·
> tesseract·kor.traineddata가 전혀 없고 `docker-compose.yml`에도 pipeline 서비스가 없다. 운영
> 컨테이너에서 파이프라인을 호출하면 즉시 종료코드 6/파일없음으로 전량 실패한다. **로컬 Windows
> venv는 개발 전용**임을 명시하고, 운영은 아래 중 하나를 채택한다.

| 옵션 | 내용 | 변경 항목 |
| --- | --- | --- |
| (A) 동일 이미지에 Python 추가 | JRE 베이스 이미지에 `apt`로 python3+venv+`tesseract-ocr`+`tesseract-ocr-kor` 설치, requirements 설치 | `backend/Dockerfile`(multi-stage Python 레이어), `docker-compose.yml` |
| (B) 사이드카/별도 서비스 | Python 파이프라인을 별도 서비스 컨테이너로 분리, Spring은 HTTP/큐로 호출(ProcessBuilder 포기) | `docker-compose.yml`에 pipeline 서비스 추가, Spring 호출부 |
| (C) multi-stage 동일 컨테이너 | 같은 컨테이너에 Python 레이어를 multi-stage로 추가 | `backend/Dockerfile` |

어느 경우든 Python 3.13 휠 가용성(PyMuPDF 등)을 검증해 인터프리터·venv 절대경로를 **계약에서
단일 고정**한다(§18). 한글·공백 포함 경로(`D:\004_대학원...`)는 `List<String>` 인자로 안전하나,
`PYTHONPATH`/cwd 한글 경로 import 이슈를 배포 환경에서 점검한다.

---
