"""API tests for /graph and /graph/data endpoints."""

import os
import sqlite3
import tempfile

import pytest

# Ensure src is importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT    NOT NULL,
    type        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    first_name  TEXT,
    last_name   TEXT,
    properties  TEXT    DEFAULT '{}',
    data_class  TEXT,
    tier        TEXT,
    source      TEXT,
    as_of       TEXT,
    created_at  REAL,
    updated_at  REAL,
    UNIQUE(agent_id, name)
);

CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT    NOT NULL,
    source_id   INTEGER NOT NULL REFERENCES nodes(id),
    target_id   INTEGER NOT NULL REFERENCES nodes(id),
    type        TEXT    NOT NULL,
    as_of       TEXT,
    source      TEXT,
    data_class  TEXT,
    tier        TEXT,
    created_at  REAL,
    UNIQUE(source_id, target_id, type)
);
"""


@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temporary Lucent DB with sample data and set env var."""
    db_path = str(tmp_path / "lucent.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO nodes (agent_id, type, name, first_name) VALUES (?, ?, ?, ?)",
        ("ada", "Person", "Daniel Stewart", "Daniel")
    )
    conn.execute(
        "INSERT INTO nodes (agent_id, type, name) VALUES (?, ?, ?)",
        ("ada", "Concept", "Python")
    )
    conn.execute(
        "INSERT INTO edges (agent_id, source_id, target_id, type) VALUES (?, ?, ?, ?)",
        ("ada", 1, 2, "KNOWS")
    )
    conn.commit()
    conn.close()

    old_val = os.environ.get("LUCENT_DB_PATH")
    os.environ["LUCENT_DB_PATH"] = db_path
    yield db_path
    if old_val is None:
        os.environ.pop("LUCENT_DB_PATH", None)
    else:
        os.environ["LUCENT_DB_PATH"] = old_val


@pytest.fixture()
def client(tmp_db):
    """TestClient that uses the tmp_db fixture."""
    # Re-import main after env var is set so LUCENT_DB picks it up
    import importlib
    import main as main_mod
    importlib.reload(main_mod)
    from starlette.testclient import TestClient
    return TestClient(main_mod.app)


def test_graph_data_returns_json(client):
    """GET /graph/data returns 200 with JSON body containing 'nodes' and 'edges'."""
    resp = client.get("/graph/data")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1


def test_graph_data_uses_lucent_db_path_env(tmp_path):
    """Endpoint reads from LUCENT_DB_PATH env var."""
    db_path = str(tmp_path / "custom.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT INTO nodes (agent_id, type, name) VALUES (?, ?, ?)",
        ("ada", "Agent", "Ada")
    )
    conn.commit()
    conn.close()

    old_val = os.environ.get("LUCENT_DB_PATH")
    os.environ["LUCENT_DB_PATH"] = db_path

    import importlib
    import main as main_mod
    importlib.reload(main_mod)
    from starlette.testclient import TestClient
    tc = TestClient(main_mod.app)

    resp = tc.get("/graph/data")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["label"] == "Ada"

    if old_val is None:
        os.environ.pop("LUCENT_DB_PATH", None)
    else:
        os.environ["LUCENT_DB_PATH"] = old_val


def test_graph_page_returns_html(client):
    """GET /graph returns 200 with HTML content type."""
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_graph_page_contains_cytoscape_reference(client):
    """GET /graph response body contains 'cytoscape' (CDN script tag)."""
    resp = client.get("/graph")
    assert "cytoscape" in resp.text.lower()


def test_graph_data_handles_missing_db(tmp_path):
    """GET /graph/data when DB does not exist returns JSON with empty nodes/edges."""
    old_val = os.environ.get("LUCENT_DB_PATH")
    os.environ["LUCENT_DB_PATH"] = str(tmp_path / "nonexistent.db")

    import importlib
    import main as main_mod
    importlib.reload(main_mod)
    from starlette.testclient import TestClient
    tc = TestClient(main_mod.app)

    resp = tc.get("/graph/data")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"] == []
    assert data["edges"] == []

    if old_val is None:
        os.environ.pop("LUCENT_DB_PATH", None)
    else:
        os.environ["LUCENT_DB_PATH"] = old_val
