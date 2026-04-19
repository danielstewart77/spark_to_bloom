"""Route tests for login and live console endpoints."""

import json
import os
import sys
import urllib.error
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auth
import main as main_mod


def _authed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    user = auth.create_user("daniel", "secret-pass", is_admin=True, replace=True)
    client = TestClient(main_mod.app)
    client.cookies.set(auth.SESSION_COOKIE_NAME, auth.create_session_token(user))
    return client


def test_console_redirects_to_login_when_unauthenticated(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/console", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=/console")


def test_console_page_renders_when_session_preload_fails(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    with patch("main._gateway_json", AsyncMock(side_effect=RuntimeError("boom"))):
        response = client.get("/console")

    assert response.status_code == 200
    assert "Hive Mind Live Console" in response.text


def test_console_page_renders_preloaded_session_cards(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    with patch("main._gateway_json", AsyncMock(return_value=[
        {"id": "sess-1", "mind_id": "nagatha", "status": "running", "last_active": 2000000001},
    ])):
        response = client.get("/console")

    assert response.status_code == 200
    assert 'data-session-id="sess-1"' in response.text
    assert "waiting for live events" in response.text


def test_login_sets_cookie_and_redirects(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    auth.create_user("daniel", "secret-pass", is_admin=True, replace=True)
    client = TestClient(main_mod.app)

    response = client.post(
        "/login",
        data={"username": "daniel", "password": "secret-pass", "next": "/console"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/console"
    assert auth.SESSION_COOKIE_NAME in response.cookies


def test_console_sessions_filters_and_sorts(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    sessions = [
        {"id": "old", "mind_id": "ada", "status": "running", "last_active": 1},
        {"id": "idle", "mind_id": "bob", "status": "idle", "last_active": 2000000000},
        {"id": "run", "mind_id": "nagatha", "status": "running", "last_active": 2000000001},
    ]

    with patch("main._gateway_json", AsyncMock(return_value=sessions)):
        response = client.get("/api/console/sessions")

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data] == ["run", "idle"]


def test_console_stream_proxies_sse(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    with patch(
        "main._proxy_session_events",
        return_value=iter(["data: {\"type\":\"assistant\",\"content\":\"hello\"}\n\n"]),
    ):
        response = client.get("/api/console/sess-1/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "assistant" in response.text


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


def test_proxy_session_events_does_not_fabricate_session_closed_on_timeout():
    with patch("main.urllib.request.urlopen", side_effect=OSError("timed out")):
        events = list(main_mod._proxy_session_events("sess-1"))

    assert events == [
        "data: " + json.dumps({"type": "system", "content": "upstream_error: timed out"}) + "\n\n"
    ]


def test_proxy_session_events_preserves_real_session_closed():
    response = _FakeResponse(
        [
            b'data: {"type":"assistant","content":"hello"}\n',
            b"\n",
            b'data: {"type":"session_closed","session_id":"sess-1"}\n',
            b"\n",
        ]
    )

    with patch("main.urllib.request.urlopen", return_value=response):
        events = list(main_mod._proxy_session_events("sess-1"))

    assert events == [
        'data: {"type":"assistant","content":"hello"}\n\n',
        'data: {"type":"session_closed","session_id":"sess-1"}\n\n',
    ]
