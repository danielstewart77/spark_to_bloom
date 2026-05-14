"""Route tests for Hive Init asset delivery."""

import os
import sys

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as main_mod


@pytest.fixture()
def hive_init_repo(tmp_path, monkeypatch):
    repo_dir = tmp_path / "hive-init"
    repo_dir.mkdir()
    (repo_dir / "hive-init.py").write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
    (repo_dir / "hive-init.sh").write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    monkeypatch.setenv("HIVE_INIT_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("HIVE_INIT_HOST", "gethivemind.sparktobloom.com")
    return repo_dir


def test_main_site_download_serves_python_installer(hive_init_repo):
    client = TestClient(main_mod.app)

    response = client.get("/downloads/hive-init.py")

    assert response.status_code == 200
    assert "text/x-python" in response.headers["content-type"]
    assert "print('ok')" in response.text


def test_hive_init_host_root_serves_landing_page(hive_init_repo):
    client = TestClient(main_mod.app)

    response = client.get("/", headers={"host": "gethivemind.sparktobloom.com"})

    assert response.status_code == 200
    assert "Get Hive Mind" in response.text
    assert "/hive-init.sh" in response.text


def test_hive_init_host_serves_shell_installer(hive_init_repo):
    client = TestClient(main_mod.app)

    response = client.get("/hive-init.sh", headers={"host": "gethivemind.sparktobloom.com"})

    assert response.status_code == 200
    assert "text/x-shellscript" in response.headers["content-type"]
    assert "echo ok" in response.text


def test_hive_init_host_unknown_asset_returns_404(hive_init_repo):
    client = TestClient(main_mod.app)

    response = client.get("/nope", headers={"host": "gethivemind.sparktobloom.com"})

    assert response.status_code == 404
