"""추출 단계 (설계 §5). pdfplumber로 텍스트(단어→줄)·표·이미지를 좌표와 함께 추출한다.

좌표계: 좌상단 원점, top=y0/bottom=y1 (point). 표 영역 단어는 본문에서 제외(영역 라우팅).
born-digital 텍스트 레이어 우선. 텍스트가 비면 해당 페이지를 scanned 로 진단(offline=OCR 미수행).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import pdfplumber


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float


@dataclass
class TableRegion:
    x0: float
    y0: float
    x1: float
    y1: float
    grid: list[list[str | None]]
    row_bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    words: list[str] = field(default_factory=list)  # bbox 내 원문 단어(읽기순) — 추출 손실 감지/폴백용


@dataclass
class ImageRegion:
    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    height: float


@dataclass
class PageData:
    page_no: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    tables: list[TableRegion] = field(default_factory=list)
    images: list[ImageRegion] = field(default_factory=list)
    body_size: float = 10.0          # 본문 추정 폰트 크기(heading 판정 기준)
    text_chars: int = 0              # 페이지 텍스트 길이(scanned 진단)
    scanned: bool = False


def _inside(cx: float, cy: float, box) -> bool:
    return box[0] - 1 <= cx <= box[2] + 1 and box[1] - 1 <= cy <= box[3] + 1


def _cluster_lines(words: list[dict], tol: float = 3.0) -> list[Line]:
    """단어를 top 기준으로 묶어 줄을 만든다. 줄 텍스트는 x0 순서로 연결."""
    if not words:
        return []
    words = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines: list[Line] = []
    cur: list[dict] = []
    cur_top = None
    for w in words:
        if cur_top is None or abs(w["top"] - cur_top) <= tol:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else cur_top
        else:
            lines.append(_mk_line(cur))
            cur = [w]
            cur_top = w["top"]
    if cur:
        lines.append(_mk_line(cur))
    return lines


def _mk_line(ws: list[dict]) -> Line:
    ws = sorted(ws, key=lambda w: w["x0"])
    text = " ".join(w["text"] for w in ws).strip()
    sizes = [w.get("size", 10.0) for w in ws if w.get("size")]
    return Line(
        text=text,
        x0=min(w["x0"] for w in ws),
        y0=min(w["top"] for w in ws),
        x1=max(w["x1"] for w in ws),
        y1=max(w["bottom"] for w in ws),
        size=round(statistics.median(sizes), 1) if sizes else 10.0,
    )


def extract_page(page) -> PageData:
    pno = page.page_number
    pd = PageData(page_no=pno, width=float(page.width), height=float(page.height))

    # 표 영역 먼저 파악(영역 라우팅: 표 단어는 본문에서 제외)
    tboxes = []
    for t in page.find_tables():
        try:
            grid = t.extract()
        except Exception:
            grid = []
        if grid:
            x0, top, x1, bottom = t.bbox
            try:
                rbb = [tuple(r.bbox) for r in t.rows]
            except Exception:
                rbb = []
            pd.tables.append(TableRegion(x0, top, x1, bottom, grid, rbb))
            tboxes.append((x0, top, x1, bottom))

    # 단어 추출(폰트 크기 포함) → 표 영역 밖만 본문 줄로. 표 영역 단어는 해당 표에 귀속(폴백용).
    words = page.extract_words(extra_attrs=["size"], keep_blank_chars=False, use_text_flow=False)
    pd.text_chars = sum(len(w["text"]) for w in words)
    twords: list[list[dict]] = [[] for _ in pd.tables]
    body_words = []
    for w in words:
        cx = (w["x0"] + w["x1"]) / 2.0
        cy = (w["top"] + w["bottom"]) / 2.0
        hit = None
        for i, b in enumerate(tboxes):
            if _inside(cx, cy, b):
                hit = i
                break
        if hit is not None:
            twords[hit].append(w)
        else:
            body_words.append(w)
    for i, tr in enumerate(pd.tables):
        ws = sorted(twords[i], key=lambda w: (round(w["top"], 1), w["x0"]))
        tr.words = [w["text"] for w in ws]
    pd.lines = [ln for ln in _cluster_lines(body_words) if ln.text]

    # 본문 폰트 크기 추정(가장 흔한 줄 크기)
    sizes = [ln.size for ln in pd.lines]
    if sizes:
        try:
            pd.body_size = statistics.mode([round(s) for s in sizes])
        except statistics.StatisticsError:
            pd.body_size = round(statistics.median(sizes))

    # 이미지
    for im in page.images:
        x0 = float(im.get("x0", 0)); x1 = float(im.get("x1", 0))
        top = float(im.get("top", 0)); bottom = float(im.get("bottom", 0))
        pd.images.append(ImageRegion(x0, top, x1, bottom, abs(x1 - x0), abs(bottom - top)))

    # scanned 진단: 텍스트가 거의 없고 이미지가 있으면 스캔 페이지로 간주(offline=처리 보류)
    if pd.text_chars < 20 and pd.images:
        pd.scanned = True
    return pd


def extract_document(pdf_path: str) -> list[PageData]:
    pages: list[PageData] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(extract_page(page))
    return pages
