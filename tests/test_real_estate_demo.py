"""Route tests for the real estate dossier workflow demo."""

import os
import sys

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


def test_real_estate_demo_redirects_when_unauthenticated(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/real-estate-demo", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=/real-estate-demo")


def test_real_estate_demo_renders_complete_workflow(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    response = client.get("/real-estate-demo")

    assert response.status_code == 200
    assert "1405 A Vermont" in response.text
    assert "2423 B Main Street" in response.text
    assert 'id="camera-input"' in response.text
    assert 'capture="environment"' in response.text
    assert 'id="voice-note-button"' in response.text
    assert 'data-workflow-step="review"' in response.text
    assert 'data-workflow-step="dossier"' in response.text


def test_canvas_embeds_real_estate_demo_split(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    response = client.get("/canvas")

    assert response.status_code == 200
    # Split layout: left whiteboard pane, right live-demo pane
    assert 'class="canvas-split"' in response.text
    assert "canvas-pane-draw" in response.text
    assert "canvas-pane-demo" in response.text
    # Right pane embeds the live real estate demo
    assert 'src="/real-estate-demo"' in response.text
    # The whiteboard itself is still present
    assert 'id="draw-surface"' in response.text
    # The send-to-Skippy poke button is present
    assert 'id="draw-submit"' in response.text
