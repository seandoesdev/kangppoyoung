"""온라인 경계 판단 provider (docs/plan/chunk_merge_impl_plan.md §3·§6).

OpenAI에 '한 섹션의 연속 청크 시퀀스에서 단위 경계가 어디인가'만 묻고(텍스트 생성 없음),
결정을 content-hash 키로 캐시한다. openai 패키지 하드 의존을 피하려 urllib로 직접 호출한다.
키가 없으면 None을 반환해 merge 스테이지가 적용되지 않게 한다(온라인 전용·명시적 게이트).
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request

from .config import Config
from .merge import member_text

_NOOP_KEYS = {"", "sk-noop"}
_API = "https://api.openai.com/v1/chat/completions"

_SYSTEM = (
    "너는 한국 정책자금 문서의 청킹 경계를 판단한다. 입력은 한 섹션 안의 연속된 텍스트 조각(atoms)이다. "
    "각 인접 조각 쌍 사이에 '업무적으로 유효한 의미 단위'의 경계가 있는지 판단하라. "
    "절차·목록·조건처럼 한 단위를 이루는 연속 조각은 하나로 묶어야 하므로 그 사이 경계는 false, "
    "주제가 바뀌어 새 단위가 시작되면 true 다. 텍스트를 생성하지 말고 경계만 판단하라. "
    'JSON 객체 {"boundaries": [bool, ...]} 만 출력하라. 길이는 정확히 (조각 수 - 1).'
)


def _has_key() -> bool:
    return os.environ.get("OPENAI_API_KEY", "").strip() not in _NOOP_KEYS


def get_boundary_decider(cfg: Config):
    """키가 있으면 OpenAI 백엔드, 없으면 None(merge 미적용)."""
    if not _has_key():
        return None
    return OpenAIBoundaryDecider(cfg)


class _Cache:
    """경계 결정 캐시(content-hash → boundaries). 재실행 결정론·재현용."""

    def __init__(self, path: str | None):
        self.path = path
        self.data: dict[str, list[bool]] = {}
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:  # noqa: BLE001 — 손상 캐시는 무시하고 새로 채운다
                self.data = {}

    def get(self, key: str):
        return self.data.get(key)

    def put(self, key: str, value: list[bool]) -> None:
        self.data[key] = value
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, sort_keys=True, indent=0)
        os.replace(tmp, self.path)


class OpenAIBoundaryDecider:
    def __init__(self, cfg: Config):
        self.model = cfg.merge_model
        self.cache = _Cache(cfg.merge_cache_path)
        self.key = os.environ["OPENAI_API_KEY"].strip()

    def decide(self, run, cfg) -> list[bool]:  # noqa: ARG002
        if len(run) <= 1:
            return []
        texts = [member_text(ch) for ch in run]
        heading_path = list(run[0].meta.heading_path)
        key = _hash(heading_path, texts)
        cached = self.cache.get(key)
        if cached is not None and len(cached) == len(texts) - 1:
            return [bool(x) for x in cached]
        bounds = self._ask(heading_path, texts)
        self.cache.put(key, bounds)
        return bounds

    def _ask(self, heading_path: list[str], texts: list[str]) -> list[bool]:
        n = len(texts)
        user = json.dumps({"heading_path": heading_path, "atoms": texts}, ensure_ascii=False)
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            _API, data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
            content = resp["choices"][0]["message"]["content"]
            bounds = json.loads(content).get("boundaries")
        except Exception:  # noqa: BLE001 — 호출/파싱 실패는 '병합 안 함'으로 안전 폴백
            return [True] * (n - 1)
        if not isinstance(bounds, list) or len(bounds) != n - 1:
            return [True] * (n - 1)
        return [bool(x) for x in bounds]


def _hash(heading_path: list[str], texts: list[str]) -> str:
    payload = json.dumps({"hp": heading_path, "t": texts}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
