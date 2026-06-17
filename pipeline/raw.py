"""중간 표현 RawChunk: 추출/구조/표/도형 단계가 공통으로 산출하고, build 가 Chunk(models)로 승격한다."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawChunk:
    content_type: str                       # ContentType.value
    page_no: int | None
    extract_method: str                     # ExtractMethod.value
    base_conf: float
    heading_path: list[str] = field(default_factory=list)
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    item: str | None = None
    page_range: tuple[int, int] | None = None
    bbox: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1
    bbox_page: int | None = None
    table_id: str | None = None
    figure_id: str | None = None
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    # payload (content_type 별로 사용)
    text: str | None = None                 # text/warning/footnote/reference/table-note/list-item
    marker: str | None = None               # list-item
    level: str | None = None                # warning level
    ref_marker: str | None = None           # footnote
    cols: list[tuple[str, str]] | None = None       # table-row
    section_path: list[str] = field(default_factory=list)
    embedding_core: str | None = None       # table-row 핵심 문장(출처꼬리표 제외)
    info_summary: str | None = None         # infographic summary
    info_ocr: str | None = None

    # 정렬 키(읽기 순서)
    order_y: float = 0.0
    order_x: float = 0.0
