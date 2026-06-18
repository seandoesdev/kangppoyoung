"""Provider 추상화 테스트 (설계 §8/§14). offline 기본 = 의미화 미수행(None) → needs_review 격리."""
from __future__ import annotations

from pipeline.config import Config
from pipeline.extract import ImageRegion
from pipeline.figures import build_figure
from pipeline.providers import OfflineVisionProvider, get_vision_provider


def test_offline_provider_returns_none():
    p = OfflineVisionProvider()
    assert p.describe(b"\x89PNG fake", "infographic") is None


def test_get_vision_provider_offline_when_cfg_offline():
    p = get_vision_provider(Config(offline=True))
    assert isinstance(p, OfflineVisionProvider)


def test_get_vision_provider_offline_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = get_vision_provider(Config(offline=False))
    assert isinstance(p, OfflineVisionProvider)


def test_get_vision_provider_offline_when_noop_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-noop")
    p = get_vision_provider(Config(offline=False))
    assert isinstance(p, OfflineVisionProvider)


def test_image_region_becomes_needs_review_offline():
    """OfflineVisionProvider 경로 → infographic 청크가 needs_review(offline_fallback)로 격리(현행 동작 보존)."""
    im = ImageRegion(x0=72.0, y0=100.0, x1=272.0, y1=300.0, width=200.0, height=200.0)
    rc = build_figure(im, page_no=1, heading_path=["제1장"], document_id="d_x", cfg=Config())
    assert rc is not None
    assert rc.content_type == "infographic"
    assert rc.needs_review is True
    assert "offline_fallback" in rc.review_reasons
