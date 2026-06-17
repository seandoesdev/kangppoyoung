"""구조 인식 (설계 §6). 마커로 heading 위계를 쌓고, 본문 줄을 text/list-item/warning/footnote 청크로 만든다."""
from __future__ import annotations

import re

from .config import Config
from .extract import Line, PageData
from .raw import RawChunk

# ─────────────────────────── 마커 정규식 ───────────────────────────
RE_CHAPTER = re.compile(r"^제\s*\d+\s*장")
RE_SECTION = re.compile(r"^제\s*\d+\s*절")
RE_REF = re.compile(r"^[\[〔]?\s*참고\s*\d+")          # [참고 1], 〔참고 2〕
RE_ARTICLE = re.compile(r"^제\s*\d+\s*조")
RE_BULLET = re.compile(r"^([•·◦▪◆◇■□•–∙])\s*")
RE_CIRCLED = re.compile(r"^([①-⑳])\s*")
RE_NUMBERED = re.compile(r"^(\d{1,2})[.)]\s+")
RE_LETTER = re.compile(r"^([가-하])[.)]\s+")
RE_DASH = re.compile(r"^([-–])\s+")
RE_WARNING = re.compile(r"^(※|⚠|주의|경고|유의)")
RE_FOOTNOTE = re.compile(r"^(\*+\d*|주\d*\))\s+")


def classify_line(text: str, size: float, body_size: float):
    """줄을 (kind, payload) 로 분류. kind ∈ heading/list/warning/footnote/text."""
    t = text.strip()
    if not t:
        return ("text", None)
    if RE_CHAPTER.match(t):
        return ("heading", (1, t))
    if RE_SECTION.match(t) or RE_REF.match(t) or RE_ARTICLE.match(t):
        return ("heading", (2, t))
    # 큰 폰트 + 짧은 줄 → 제목으로 추정
    if size >= body_size * 1.3 and len(t) <= 40 and not t.endswith((".", "다", "음", "함")):
        return ("heading", (2, t))
    if RE_WARNING.match(t):
        return ("warning", None)
    if RE_FOOTNOTE.match(t):
        m = RE_FOOTNOTE.match(t)
        return ("footnote", m.group(1))
    for rx in (RE_BULLET, RE_CIRCLED, RE_NUMBERED, RE_LETTER, RE_DASH):
        m = rx.match(t)
        if m:
            return ("list", m.group(0))   # 마커 전체(구두점 포함) 보존
    return ("text", None)


class HeadingTracker:
    """heading 스택 + y좌표 체크포인트(표/이미지가 활성 heading_path를 조회)."""

    def __init__(self):
        self.stack: list[tuple[int, str]] = []
        self.checkpoints: list[tuple[float, list[str], str | None, str | None]] = []

    def push(self, level: int, text: str, y: float):
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, text))
        self.checkpoints.append((y, self.path(), self.chapter(), self.section()))

    def path(self) -> list[str]:
        return [t for _, t in self.stack]

    def chapter(self) -> str | None:
        for lvl, t in self.stack:
            if lvl == 1:
                return t
        return None

    def section(self) -> str | None:
        for lvl, t in self.stack:
            if lvl == 2:
                return t
        return None


# 본문 줄 처리는 build.py가 표/이미지와 수직 순서로 인터리브하며 수행한다(heading 상태가
# 페이지를 넘어 지속되므로). 여기서는 classify_line + HeadingTracker만 제공한다.
