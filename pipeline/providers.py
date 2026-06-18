"""Vision/LLM Provider 추상화 (설계 §8/§14).

offline 기본: 의미화를 수행하지 않고 None을 반환해, 호출자(figures 등)가 비텍스트를
needs_review로 격리하게 한다. 결정적(외부호출 0). 키 주입 시에만 OpenAI 백엔드로 위임하되,
openai 패키지는 지연 임포트(try/except ImportError → offline 폴백)하여 하드 의존을 만들지 않는다.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from .config import Config

_NOOP_KEYS = {"", "sk-noop"}


@runtime_checkable
class VisionProvider(Protocol):
    def describe(self, image_png: bytes, hint: str) -> dict | None:
        """이미지를 의미화한 dict(§11.3 Content 필드)나, 의미화 불가 시 None을 반환한다."""
        ...


class OfflineVisionProvider:
    """offline 폴백: 의미화를 수행하지 않는다(결정적). 항상 None → 호출자가 needs_review 격리."""

    def describe(self, image_png: bytes, hint: str) -> dict | None:  # noqa: ARG002
        return None


def _has_openai_key() -> bool:
    return os.environ.get("OPENAI_API_KEY", "").strip() not in _NOOP_KEYS


def get_vision_provider(cfg: Config) -> VisionProvider:
    """cfg.offline 또는 키 없음이면 OfflineVisionProvider. 키가 있으면 OpenAI 백엔드를
    지연 임포트로 시도하고, 임포트 실패 시 offline으로 폴백한다(하드 의존 회피)."""
    if cfg.offline or not _has_openai_key():
        return OfflineVisionProvider()
    try:
        from .providers_openai import OpenAIVisionProvider  # 선택적 백엔드(미설치 가능)
    except ImportError:
        return OfflineVisionProvider()
    return OpenAIVisionProvider(cfg)
