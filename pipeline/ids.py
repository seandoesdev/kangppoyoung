"""결정적 식별자 (설계 §13). 동일 입력 → 동일 ID. 타임스탬프·UUID·난수 미포함."""
from __future__ import annotations

import hashlib
import unicodedata

_US = b"\x1f"  # 구분자


def make_document_id(pdf_bytes: bytes) -> str:
    return "d_" + hashlib.sha256(pdf_bytes).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_float(x: float) -> str:
    """bbox/격자 좌표 0.1pt 라운딩(canonical). 부동소수 미세변동이 ID를 흔들지 않게."""
    return f"{round(float(x), 1):.1f}"


def norm_text(s: str) -> str:
    """공백 정리 + 유니코드 NFC."""
    return unicodedata.normalize("NFC", " ".join((s or "").split()))


def page_anchor(page_no: int | None, page_range: tuple[int, int] | None) -> str:
    if page_range:
        return f"p{page_range[0]}-{page_range[1]}"
    return f"p{page_no}"


def make_chunk_id(
    document_id: str,
    content_type: str,
    page_anchor_: str,
    structural_path: str,
    norm_content: str,
    seq: int,
) -> str:
    h = hashlib.sha256()
    for part in (document_id, content_type, page_anchor_, structural_path, norm_content, str(seq)):
        h.update(part.encode("utf-8"))
        h.update(_US)
    return "c_" + h.hexdigest()[:24]


def make_table_id(document_id: str, page_anchor_: str, grid_signature: str) -> str:
    h = hashlib.sha256(f"{document_id}|{page_anchor_}|{grid_signature}".encode("utf-8"))
    return "tbl_" + h.hexdigest()[:8]


def make_figure_id(document_id: str, page_anchor_: str, norm_bbox: str) -> str:
    h = hashlib.sha256(f"{document_id}|{page_anchor_}|{norm_bbox}".encode("utf-8"))
    return "fig_" + h.hexdigest()[:8]


def structural_path(heading_path: list[str], prefix: str | None = None) -> str:
    body = _US.decode("latin1").join(heading_path or [])
    return f"{prefix}#{body}" if prefix else body
