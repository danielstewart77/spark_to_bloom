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
    assert "watching live events" in response.text


def test_console_page_renders_user_menu_control(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    with patch("main._gateway_json", AsyncMock(return_value=[])):
        response = client.get("/console")

    assert response.status_code == 200
    assert "user-menu-button" in response.text
    assert "log out" in response.text


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


def test_build_terminal_selector_groups_active_sessions_per_mind():
    now = int(__import__("time").time())
    minds = [
        {"id": "ada-id", "name": "ada"},
        {"id": "bilby-id", "name": "bilby"},
    ]
    sessions = [
        {"id": "sess-1", "mind_id": "ada-id", "status": "running", "last_active": now - 30, "summary": "hello world"},
        {"id": "sess-2", "mind_id": "ada-id", "status": "closed", "last_active": now - 60, "summary": ""},
        {"id": "sess-3", "mind_id": "ada-id", "status": "idle", "last_active": now - 90, "summary": "older"},
        {"id": "sess-4", "mind_id": "bilby-id", "status": "running", "last_active": now - 86500, "summary": "too old"},
        {"id": "sess-5", "mind_id": "unknown-id", "status": "running", "last_active": now - 10, "summary": "orphan"},
    ]
    out = main_mod._build_terminal_selector(minds, sessions)
    assert len(out) == 2
    ada = out[0]
    assert ada["name"] == "ada"
    assert [s["id"] for s in ada["sessions"]] == ["sess-1", "sess-3"]
    assert ada["sessions"][0]["short_id"] == "sess-1"[:8]
    assert ada["sessions"][0]["age"].endswith("ago")
    bilby = out[1]
    assert bilby["name"] == "bilby"
    assert bilby["sessions"] == []


def test_terminal_page_renders_selector_with_session_options(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    now = int(__import__("time").time())

    async def fake_gateway_json(path: str, *args, **kwargs):
        if path == "/broker/minds":
            return [{"id": "ada-id", "name": "ada"}]
        if path == "/sessions":
            return [
                {"id": "sess-abcdef123", "mind_id": "ada-id", "status": "running",
                 "last_active": now - 5, "summary": "do the thing"},
            ]
        return []

    with patch("main._gateway_json", side_effect=fake_gateway_json):
        response = client.get("/terminal")

    assert response.status_code == 200
    body = response.text
    assert 'value="new:ada-id"' in body
    assert 'value="session:sess-abcdef123"' in body
    assert "do the thing" in body


def test_api_terminal_selector_returns_grouped_payload(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    now = int(__import__("time").time())

    async def fake_gateway_json(path: str, *args, **kwargs):
        if path == "/broker/minds":
            return [{"id": "ada-id", "name": "ada"}]
        if path == "/sessions":
            return [
                {"id": "sess-xyz", "mind_id": "ada-id", "status": "idle",
                 "last_active": now - 120, "summary": "x"},
            ]
        return []

    with patch("main._gateway_json", side_effect=fake_gateway_json):
        response = client.get("/api/terminal/selector")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "ada"
    assert payload[0]["sessions"][0]["id"] == "sess-xyz"
