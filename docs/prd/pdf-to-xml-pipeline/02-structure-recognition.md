# Step 2 · 요소·구조 인식 (Structure Recognition) — PDF → RAG Chunk 파이프라인

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §6 · 선행 참조: 00-foundation, 01-extraction
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 6. 요소·구조 인식 (Structure Recognition)

추출된 RawSpan(text, bbox, page, source)을 입력으로, 규칙 엔진이 한국 규정 번호체계를 인식해
heading 위계와 content_type을 부여한다.

**마커 규칙(정규식 + 레이아웃 보조 신호)**

| 위계 | 마커 패턴 | meta 필드 |
| --- | --- | --- |
| 편 | `^제\d+편` | chapter 상위(heading_path) |
| 장 | `^제\d+장` | chapter |
| 절 | `^제\d+절` | section |
| 관 | `^제\d+관` | subsection |
| 조 | `^제\d+조(의\d+)?` | (조 단위 컨테이너), item에 원표기 |
| 항 | `①`~`⑳`, `㉑`~`㊿`, `제\d+항` | item |
| 호 | `^\d+\.` | item (들여쓰기·부모 컨텍스트로 항/단순나열 모호성 해소) |
| 목 | `^[가-하]\.` | item |
| 부칙/별표/서식 | `부칙`, `별표 \d+`, `서식 제\d+호` 헤더 | heading_path 분기 |

**content_type 파생**: 일반 문단=`text`, 번호/불릿 목록 항목=`list-item`(marker 보존), 경고
박스=`warning`, 각주=`footnote`, 상호참조("별표 1 참조")=`reference`. 표/그림/순서도/스크린샷은
영역 라우팅(§5)에서 분기된다.

**heading 스택**: heading 마커를 만나면 같거나 하위 레벨을 pop하고 push한다. 각 청크는 현재
스택 스냅샷을 `heading_path`로 받는다(예: `["제3장","2절","2.1 데이터 수집","OCR 처리"]`). 이
`heading_path`는 §11.1 `SourceLocation.heading_path`에도 그대로 복제되어, 출처가 SourceLocation
단독으로 장·절·항까지 자기완결되게 한다.

```python
def assign_relations(chunks: list[Chunk]) -> None: ...  # heading_path/parent/prev/next/related (§10)
```

> '의미 단위' 청크 경계(본문 과분할/과병합)와 heading_path(장-절-항) 복원은 한국 규정 번호체계
> 파서 품질에 의존한다. 오분류 시 parent/heading_path가 틀려 문맥 복원·관계 메타가 약화되므로,
> 미커버 마커·모호 경계는 `review_required`로 위임한다.

---
