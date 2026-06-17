"""오케스트레이터: PDF → Chunk 모델 리스트.

페이지별로 본문 줄·표·이미지를 수직 순서로 인터리브 처리(heading 상태는 페이지를 넘어 지속)하고,
RawChunk를 모은 뒤 결정적 chunk_id·source_location·신뢰도를 부여해 Chunk 모델로 승격, 관계를 연결한다.
"""
from __future__ import annotations

import os
import statistics

from . import figures as F
from . import ids as I
from . import models as M
from . import relations as R
from . import tables as T
from .config import Config
from .extract import PageData, extract_document
from .raw import RawChunk
from .structure import HeadingTracker, classify_line

_VISUAL = {"infographic", "screenshot", "flowchart", "flowchart-edge", "graph", "procedure-step"}
_TEXTLIKE = {"text", "list-item", "warning", "footnote", "reference", "table-note"}


def build_chunks(pdf_path: str, cfg: Config) -> tuple[list[M.Chunk], dict]:
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    document_id = I.make_document_id(pdf_bytes)
    source_sha = I.sha256_hex(pdf_bytes)
    file_name = os.path.basename(pdf_path)

    pages = extract_document(pdf_path)
    tracker = HeadingTracker()
    raws: list[RawChunk] = []
    for pd in pages:
        raws.extend(_process_page(pd, tracker, document_id, cfg))

    raws.sort(key=lambda r: (r.page_no or 0, round(r.order_y, 1), round(r.order_x, 1)))
    chunks = _to_models(raws, document_id, file_name, cfg)
    R.link(chunks)

    doc_info = {
        "document_id": document_id,
        "source_sha256": source_sha,
        "file_name": file_name,
        "pages": len(pages),
        "scanned_pages": sum(1 for p in pages if p.scanned),
    }
    return chunks, doc_info


def _process_page(pd: PageData, tracker: HeadingTracker, document_id: str, cfg: Config) -> list[RawChunk]:
    out: list[RawChunk] = []
    events: list[tuple] = []
    for ln in pd.lines:
        events.append((ln.y0, ln.x0, "line", ln))
    for t in pd.tables:
        events.append((t.y0, t.x0, "table", t))
    for im in pd.images:
        events.append((im.y0, im.x0, "image", im))
    events.sort(key=lambda e: (round(e[0], 1), e[1]))

    heights = [l.y1 - l.y0 for l in pd.lines if l.y1 > l.y0]
    lh = statistics.median(heights) if heights else 10.0

    para: list = []
    prev_y1 = [None]

    def flush():
        if para:
            text = " ".join(l.text for l in para).strip()
            if text:
                out.append(_text_raw(pd, tracker, para, "text", text))
        para.clear()

    for y, x, kind, obj in events:
        if kind == "line":
            ln = obj
            cl, payload = classify_line(ln.text, ln.size, pd.body_size)
            gap = (ln.y0 - prev_y1[0]) if prev_y1[0] is not None else 0.0
            prev_y1[0] = ln.y1
            if cl == "heading":
                flush()
                tracker.push(payload[0], payload[1], ln.y0)
                # heading 텍스트도 독립 text 청크로 보존(섹션 제목 = 검색 단위 + 텍스트 무손실).
                # heading_path 브레드크럼과 별개로 content에도 남겨 누락을 방지한다.
                out.append(_text_raw(pd, tracker, [ln], "text", ln.text.strip()))
            elif cl == "list":
                flush()
                prefix = payload                    # 마커 전체(구두점·공백 포함)
                body = ln.text.strip()[len(prefix):].strip()
                marker = prefix.strip()
                rc = _text_raw(pd, tracker, [ln], "list-item", body or marker)
                rc.marker = marker
                rc.item = marker
                out.append(rc)
            elif cl == "warning":
                flush()
                out.append(_text_raw(pd, tracker, [ln], "warning", ln.text.strip()))
            elif cl == "footnote":
                flush()
                rc = _text_raw(pd, tracker, [ln], "footnote", ln.text.strip())
                rc.ref_marker = payload
                out.append(rc)
            else:  # text
                if para and gap > lh * 1.8:
                    flush()
                para.append(ln)
                if sum(len(l.text) for l in para) >= cfg.max_chunk_chars:
                    flush()
        elif kind == "table":
            flush()
            out.extend(T.build_table_chunks(obj, pd.page_no, tracker.path(), document_id, cfg))
        elif kind == "image":
            flush()
            rc = F.build_figure(obj, pd.page_no, tracker.path(), document_id, cfg)
            if rc:
                out.append(rc)
    flush()
    return out


def _text_raw(pd: PageData, tracker: HeadingTracker, lines: list, ctype: str, text: str) -> RawChunk:
    x0 = min(l.x0 for l in lines); y0 = min(l.y0 for l in lines)
    x1 = max(l.x1 for l in lines); y1 = max(l.y1 for l in lines)
    return RawChunk(
        content_type=ctype,
        page_no=pd.page_no,
        extract_method="pdf_text",
        base_conf=0.95,
        heading_path=list(tracker.path()),
        chapter=tracker.chapter(),
        section=tracker.section(),
        bbox=(x0, y0, x1, y1),
        bbox_page=pd.page_no,
        text=text,
        order_y=y0,
        order_x=x0,
    )


def _norm_content(r: RawChunk) -> str:
    if r.content_type in _VISUAL:
        return ""
    if r.content_type == "table-row":
        return I.norm_text("|".join(f"{n}={v}" for n, v in sorted(r.cols or [])))
    return I.norm_text((r.marker or "") + (r.text or ""))


def _to_models(raws: list[RawChunk], document_id: str, file_name: str, cfg: Config) -> list[M.Chunk]:
    seqc: dict[tuple, int] = {}
    chunks: list[M.Chunk] = []
    for r in raws:
        # 빈 텍스트형 청크 제거(노이즈)
        if r.content_type in _TEXTLIKE and not (r.text or "").strip():
            continue

        pa = I.page_anchor(r.page_no, r.page_range)
        prefix = r.table_id or r.figure_id
        spath = I.structural_path(r.heading_path, prefix)
        normc = _norm_content(r)
        key = (pa, spath, r.content_type)
        seq = seqc.get(key, 0)
        seqc[key] = seq + 1
        chunk_id = I.make_chunk_id(document_id, r.content_type, pa, spath, normc, seq)

        conf = r.base_conf
        reasons = list(r.review_reasons)
        review = r.needs_review
        if conf < cfg.confidence_threshold:
            review = True
            if "low_confidence" not in reasons:
                reasons.append("low_confidence")

        bbox = None
        if r.bbox:
            bbox = M.BBox(page=r.bbox_page, x0=r.bbox[0], y0=r.bbox[1], x1=r.bbox[2], y1=r.bbox[3])
        locator = " > ".join(r.heading_path) if r.heading_path else None
        sl = M.SourceLocation(
            file_name=file_name, document_id=document_id, page_no=r.page_no, page_range=r.page_range,
            bbox=bbox, extract_method=M.ExtractMethod(r.extract_method), heading_path=list(r.heading_path),
            locator=locator, table_id=r.table_id, figure_id=r.figure_id,
        )
        meta = M.Meta(
            chunk_id=chunk_id, document_id=document_id, file_name=file_name,
            page_no=r.page_no, page_range=r.page_range, content_type=M.ContentType(r.content_type),
            chapter=r.chapter, section=r.section, subsection=r.subsection, item=r.item,
            heading_path=list(r.heading_path), table_id=r.table_id, figure_id=r.figure_id,
            extract_method=M.ExtractMethod(r.extract_method), confidence=conf, bbox=bbox,
            related_chunk_ids=[], source_location=sl, needs_review=review, review_reasons=reasons,
        )
        chunks.append(M.Chunk(meta=meta, content=_content(r)))
    return chunks


def _content(r: RawChunk) -> M.Content:
    ct = r.content_type
    if ct == "text":
        return M.TextContent(text=r.text)
    if ct == "list-item":
        return M.ListItemContent(marker=r.marker, text=r.text)
    if ct == "warning":
        return M.WarningContent(text=r.text, level=r.level)
    if ct == "footnote":
        return M.FootnoteContent(text=r.text, ref_marker=r.ref_marker)
    if ct == "table-note":
        return M.TableNoteContent(text=r.text)
    if ct == "reference":
        return M.ReferenceContent(text=r.text)
    if ct == "table-row":
        return M.TableRowContent(
            cols=[M.Col(name=n, value=v) for n, v in (r.cols or [])],
            section_path=list(r.section_path), embedding_text=r.embedding_core or "",
        )
    if ct == "infographic":
        return M.InfographicContent(summary=r.info_summary or "", ocr_text=r.info_ocr)
    raise NotImplementedError(f"content_type 미지원: {ct}")
