"""파이프라인 구성 (설계 §19). 임계값·언어·모드를 한곳에 모은다."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # 신뢰도/검토
    confidence_threshold: float = 0.7          # 미만이면 needs_review(low_confidence)
    table_confidence_threshold: float = 0.6    # 미만이면 표 구조화 포기(table_fallback)
    table_word_coverage_min: float = 0.90      # 표 추출이 원문 단어를 이만큼 못 담으면 text 폴백(무손실)

    # 추출/모드
    ocr_lang: str = "kor+eng"
    offline: bool = True                       # tesseract/LLM 미사용(키 없는 환경 기본)
    vision: str = "off"                        # off|auto

    # 청킹
    max_chunk_chars: int = 800                 # 일반 본문 청크 상한
    min_image_area_pt: float = 2500.0          # 이 면적 미만 이미지는 장식으로 보고 스킵

    # 입력 가드
    max_input_mb: int = 100
    max_pages: int = 300

    # 베이스 confidence (extract_method별, §15.1)
    base_conf_pdf_text: float = 0.95
    base_conf_layout: float = 0.8
    base_conf_ocr: float = 0.3
