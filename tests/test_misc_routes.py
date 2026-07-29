"""Route tests for miscellaneous app surface behaviour."""

import os
import sys

from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as main_mod


def test_about_path_returns_404_not_500(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/about")

    assert response.status_code == 404


def test_hive_mind_showcase_is_public_and_links_from_home(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    showcase = client.get("/hive-mind")
    home = client.get("/")

    assert showcase.status_code == 200
    assert "One intelligence" in showcase.text
    assert "git clone https://github.com/danielstewart77/hive-mind.git" in showcase.text
    assert "One inference gateway" in showcase.text
    assert "https://github.com/danielstewart77/inference-proxy" in showcase.text
    assert "6 capabilities" in showcase.text
    assert "/static/images/hive/terminal-grid.png" in showcase.text
    assert 'href="/hive-mind"' in home.text
