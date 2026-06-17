# Step 6 · 관계 그래프 빌드 (Relation Graph) — PDF → RAG Chunk 파이프라인

> 설계 세부 문서 · [개요·문서 맵](../pdf-to-xml-pipeline.md) · 버전 v0.2 · 최종 수정 2026-06-17
> 담는 섹션: §10 · 선행 참조: 00-foundation (+ 전 step 산출 청크)
> 섹션 번호(§N)는 분리 후에도 전역 고정 식별자다. 다른 섹션은 개요의 **문서 맵**으로 찾는다.

---

## 10. 관계 그래프 빌드 (Relation Graph)

parent / previous / next / related / heading_path를 결정적으로 빌드한다. 입력은 읽기 순서가
고정된 청크 목록(page asc, y asc, x asc; 표 내부 row asc). chunk_id가 콘텐츠 해시라 관계 빌드
**전에** 확정되므로 순서 의존성·순환 없이 2-pass가 성립한다.

### 10.1 Pass 1 — 위계·순서 확정 (단일 순회)

heading 스택을 유지하며 각 청크의 구조 메타·heading_path·parent·prev/next를 확정한다.

```
heading_stack = []; prev = None
for ch in sorted_chunks:
    if ch.is_heading:
        pop_stack_until(level < ch.level); heading_stack.append((ch.level, ch.heading_text))
    ch.meta.heading_path = [t for _, t in heading_stack]
    ch.meta.chapter/section/subsection/item = project(heading_stack)
    ch.meta.parent_chunk_id = nearest_container_id(heading_stack, ch)
    if prev: prev.meta.next_chunk_id = ch.id; ch.meta.previous_chunk_id = prev.id
    prev = ch
```

parent 규칙(타입별 override): 문단/목록/경고/참고/각주 → 가장 가까운 절/장 청크; 표 Record/표
주석 → 그 표의 헤더 청크(`c_{table_id}_hdr`); 절차 단계 → 절차 컨테이너; 순서도 노드/관계 →
순서도 graph 청크. prev/next는 **분할표 논리 병합 후** 순서로 매긴다(페이지 경계로 끊지 않음).

### 10.2 Pass 2 — related 양방향 (인덱스 기반)

구조만으로 안 잡히는 의미 연관을 결정적 규칙으로 양방향 연결한다.

```
by_table  : table_id  -> {header, rows[], notes[]}
by_figure : figure_id -> {nodes[], edges[], steps[], desc[]}
by_ref    : ref_target_hint("별표 1","제3조") -> 대상 청크 id

link(notes <-> rows)   link(header <-> rows)        # 표설명 ↔ Record
link(edges <-> nodes)  link(desc <-> steps)         # 순서도 관계 ↔ 노드, 그림설명 ↔ 절차단계
link(src   <-> tgt)    # 본문 참조("별표 1에 따라") ↔ 대상 표/조항
# 마감: related_chunk_ids = sorted(set(...))  → 재실행 안정
```

**결정성**: 모든 순회는 정렬된 키(chunk_id/seq)로, related는 `sorted(set())`로 마감 → 재실행 시
동일 그래프. 고아 검사: parent/related가 가리키는 id가 청크 집합에 없으면 manifest 경고 + 링크
드롭(dangling 방지).

---
