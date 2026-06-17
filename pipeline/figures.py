"""비텍스트 의미화 (설계 §8) — offline 경로.

Vision/LLM 미사용(키·tesseract 없음) 환경에서는 이미지를 의미화하지 못하므로,
도형/인포그래픽을 저신뢰 infographic 청크로 만들고 needs_review(offline_fallback)로 격리한다.
(키 주입 시 OpenAI Vision provider로 교체 — providers.py)
"""
from __future__ import annotations

from .config import Config
from .extract import ImageRegion, PageData
from .ids import make_figure_id, norm_float
from .raw import RawChunk

_PLACEHOLDER = "[비텍스트 시각자료 — offline 모드에서 자동 의미화를 수행하지 못함(검토 필요)]"


def build_figure(
    im: ImageRegion, page_no: int, heading_path: list[str], document_id: str, cfg: Config
) -> RawChunk | None:
    """이미지 1개 → infographic 청크(offline 폴백). 장식 추정(작은 면적)은 None 반환."""
    if im.width * im.height < cfg.min_image_area_pt:
        return None
    nb = "|".join(norm_float(v) for v in (im.x0, im.y0, im.x1, im.y1))
    figure_id = make_figure_id(document_id, f"p{page_no}", nb)
    return RawChunk(
        content_type="infographic",
        page_no=page_no,
        extract_method="layout_analysis",
        base_conf=cfg.base_conf_ocr,  # 0.3 — 의미화 미수행
        heading_path=list(heading_path),
        chapter=heading_path[0] if heading_path else None,
        section=(heading_path[1] if len(heading_path) > 1 else None),
        bbox=(im.x0, im.y0, im.x1, im.y1),
        bbox_page=page_no,
        figure_id=figure_id,
        info_summary=_PLACEHOLDER,
        needs_review=True,
        review_reasons=["offline_fallback"],
        order_y=im.y0,
        order_x=im.x0,
    )
