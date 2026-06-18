"""라이브 스택 E2E 테스트 (nginx → backend → MySQL 벡터DB).

docker compose 로 띄운 전체 스택을 프론트가 접근하는 것과 동일한 경로(nginx 엣지)로 검증한다.
스택이 떠 있지 않으면 자동 skip 한다(단위/파이프라인 테스트 흐름을 막지 않음).

실행 전제:
    docker compose up --build -d   # NGINX_PORT(.env, 기본 8088)
환경변수 E2E_BASE_URL 로 베이스 URL override 가능(기본 http://localhost:8088).

이 테스트는 Testcontainers(JDK25/Windows 비호환) 통합테스트를 대체하여, 실제 적재된
벡터DB에 대한 검색·이력·예시 CRUD 동작을 라이브로 검증한다.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8088")
API = BASE + "/api/v1"


def _req(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def _stack_up() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _stack_up(), reason=f"라이브 스택({BASE}) 미기동 — E2E skip")


def test_spa_served_through_nginx():
    with urllib.request.urlopen(BASE + "/", timeout=10) as r:
        html = r.read().decode("utf-8", "replace")
    assert r.status == 200
    assert 'id="root"' in html        # React SPA 마운트 지점
    assert "assets/" in html          # vite 번들 참조


def test_search_returns_evidence_from_vector_db():
    status, body = _req("POST", "/search", {"query": "정책자금 융자 신청 절차와 지원 대상"})
    assert status == 200
    assert body["answer"]                      # 비어있지 않은 답변
    assert isinstance(body["evidence"], list)
    assert len(body["evidence"]) > 0           # 벡터DB에서 근거 조항 반환
    ev = body["evidence"][0]
    for key in ("docId", "docTitle", "docType", "articleNo", "text"):
        assert key in ev
    assert ev["text"].strip()                  # 근거 원문 존재


def test_search_blank_query_returns_400():
    status, _ = _req("POST", "/search", {"query": ""})
    assert status == 400                        # @NotBlank 검증


def test_search_history_records_latest_query():
    marker = "이력검증질의_정책자금_E2E"
    _req("POST", "/search", {"query": marker})
    status, history = _req("GET", "/search/history?page=0&size=20")
    assert status == 200
    assert isinstance(history, list)
    assert any(h.get("query") == marker for h in history)


def test_examples_crud_roundtrip():
    status, created = _req("POST", "/search/examples", {"text": "E2E 예시 질문"})
    assert status in (200, 201)
    ex_id = created["id"]
    status, items = _req("GET", "/search/examples")
    assert status == 200
    assert any(x["id"] == ex_id for x in items)
    status, _ = _req("DELETE", f"/search/examples/{ex_id}")
    assert status in (200, 204)
