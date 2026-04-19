"""Route tests for login and live console endpoints."""

import os
import sys
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
