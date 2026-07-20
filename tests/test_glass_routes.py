"""Routes for the Hive Glass observability panel."""

import asyncio
import json
import os
import sys
from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import auth
import main as main_mod

from test_console_routes import (  # noqa: E402
    _FakeAsyncClient,
    _FakeStreamResponse,
    _authed_client,
    _collect,
)


def test_glass_page_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    auth.create_user("daniel", "secret-pass", is_admin=True, replace=True)
    client = TestClient(main_mod.app)
    response = client.get("/glass", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in response.headers["location"]


def test_glass_page_renders_panel(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    response = client.get("/glass")
    assert response.status_code == 200
    body = response.text
    assert 'id="glass-fleet"' in body
    assert 'id="glass-lanes"' in body
    assert 'id="glass-log"' in body
    # stall highlighting + actions are the point of the panel
    assert "g-stuck" in body
    assert "/api/console/" in body and "/interrupt" in body
    assert "/api/terminal/session/" in body


def test_api_glass_fleet_proxies_gateway(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    async def fake_gateway_json(path, *a, **kw):
        assert path == "/glass/fleet"
        return {"minds": [{"mind_id": "m1", "name": "arnold", "healthy": True,
                           "open_sessions": 1, "last_active": 123.0}]}

    with patch("main._gateway_json", side_effect=fake_gateway_json):
        response = client.get("/api/glass/fleet")

    assert response.status_code == 200
    assert response.json()["minds"][0]["name"] == "arnold"


def test_api_glass_turns_proxies_gateway(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    async def fake_gateway_json(path, *a, **kw):
        assert path == "/glass/turns"
        return {"turns": [{"hop": "received", "session_id": "s1", "ts": 1.0}]}

    with patch("main._gateway_json", side_effect=fake_gateway_json):
        response = client.get("/api/glass/turns")

    assert response.status_code == 200
    assert response.json()["turns"][0]["hop"] == "received"


def test_glass_stream_sets_sse_headers(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    async def fake_proxy(path, params=None):
        yield "data: {\"hop\":\"ping\"}\n\n"

    with patch("main._proxy_gateway_sse", side_effect=fake_proxy):
        response = client.get("/api/glass/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "no-transform" in response.headers["cache-control"]
    assert response.headers["x-accel-buffering"] == "no"


def test_proxy_gateway_sse_relays_data_lines_and_errors():
    lines = ['data: {"hop":"received","session_id":"s1"}', ""]
    fake_client = _FakeAsyncClient(_FakeStreamResponse(lines))
    with patch("main.httpx.AsyncClient", return_value=fake_client):
        events = asyncio.run(_collect(main_mod._proxy_gateway_sse("/glass/stream")))
    assert events == ['data: {"hop":"received","session_id":"s1"}\n\n']

    err = httpx.HTTPStatusError(
        "boom", request=httpx.Request("GET", "http://x"),
        response=httpx.Response(502),
    )
    fake_client = _FakeAsyncClient(_FakeStreamResponse([], raise_for_status_error=err))
    with patch("main.httpx.AsyncClient", return_value=fake_client):
        events = asyncio.run(_collect(main_mod._proxy_gateway_sse("/glass/stream")))
    payload = json.loads(events[0][len("data: "):])
    assert payload["type"] == "error"
    assert "502" in payload["detail"]
