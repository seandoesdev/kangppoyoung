"""embedding_text 파생 (설계 §12.2). 항상 자연어 + 짧은 출처 꼬리표를 붙여 검색 품질·출처를 보장한다."""
from __future__ import annotations

from . import models as M


def _page_label(meta: M.Meta) -> str:
    if meta.page_range:
        return f"p.{meta.page_range[0]}-{meta.page_range[1]}"
    return f"p.{meta.page_no}"


def _locator(meta: M.Meta) -> str:
    return " > ".join(meta.heading_path) if meta.heading_path else "본문"


def source_tail(meta: M.Meta) -> str:
    return f" (출처: {meta.file_name} {_page_label(meta)}, {_locator(meta)})"


def embedding_text(chunk: M.Chunk) -> str:
    c = chunk.content
    m = chunk.meta
    tail = source_tail(m)
    k = c.kind
    if k in ("text", "warning", "footnote", "reference", "table-note"):
        return c.text.strip() + tail
    if k == "list-item":
        head = m.heading_path[-1] if m.heading_path else ""
        marker = (c.marker + " ") if c.marker else ""
        body = f"{head}: {marker}{c.text}".strip(": ").strip()
        return body + tail
    if k == "table-row":
        return c.embedding_text.strip() + tail
    if k == "procedure-step":
        acts = " ".join(c.actions)
        return f"단계 {c.step_no or ''}: {c.step_label or ''} {acts}".strip() + tail
    if k == "infographic":
        dp = ", ".join(f"{d.name} {d.value}" for d in c.data_points)
        parts = [c.summary]
        if c.reading:
            parts.append(c.reading)
        if dp:
            parts.append(dp)
        return " ".join(p for p in parts if p) + tail
    if k == "screenshot":
        acts = ", ".join(f"{a.verb} {a.target}" + (f" {a.value}" if a.value else "") for a in c.actions)
        return f"{c.purpose} {acts}".strip() + tail
    if k in ("flowchart", "graph"):
        return (getattr(c, "semantics", None) or getattr(c, "summary", "")).strip() + tail
    if k == "flowchart-edge":
        cond = f" ({c.condition})" if c.condition else ""
        return f"{c.from_node} → {c.to_node}{cond}: {c.relation}".strip() + tail
    return tail.strip()
