"""Unit tests for graph_data module -- SQLite graph extraction logic."""

import sqlite3
import os
import tempfile
import pytest


# The graph_data module lives in src/, so adjust path for import
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_data import get_graph_data


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


def _make_test_db(tmp_path: str) -> str:
    """Create a test SQLite database with the Lucent schema. Returns db path."""
    db_path = os.path.join(tmp_path, "lucent.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.close()
    return db_path


def _insert_node(db_path: str, agent_id: str, node_type: str, name: str,
                 first_name: str | None = None, last_name: str | None = None,
                 properties: str = "{}") -> int:
    """Insert a node and return its id."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO nodes (agent_id, type, name, first_name, last_name, properties) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, node_type, name, first_name, last_name, properties)
    )
    node_id = cur.lastrowid
    conn.commit()
    conn.close()
    return node_id


def _insert_edge(db_path: str, agent_id: str, source_id: int,
                 target_id: int, edge_type: str) -> None:
    """Insert an edge."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO edges (agent_id, source_id, target_id, type) VALUES (?, ?, ?, ?)",
        (agent_id, source_id, target_id, edge_type)
    )
    conn.commit()
    conn.close()


def test_returns_nodes_and_edges(tmp_path):
    """Function returns dict with 'nodes' and 'edges' keys from populated DB."""
    db_path = _make_test_db(str(tmp_path))
    n1 = _insert_node(db_path, "ada", "Person", "Daniel")
    n2 = _insert_node(db_path, "ada", "Concept", "Python")
    _insert_edge(db_path, "ada", n1, n2, "KNOWS")

    result = get_graph_data(db_path)

    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1


def test_node_structure_has_required_fields(tmp_path):
    """Each node has 'id', 'label', 'type' keys."""
    db_path = _make_test_db(str(tmp_path))
    _insert_node(db_path, "ada", "Person", "Daniel")

    result = get_graph_data(db_path)
    node = result["nodes"][0]

    assert "id" in node
    assert "label" in node
    assert "type" in node


def test_edge_structure_has_required_fields(tmp_path):
    """Each edge has 'source', 'target', 'label' keys."""
    db_path = _make_test_db(str(tmp_path))
    n1 = _insert_node(db_path, "ada", "Person", "Daniel")
    n2 = _insert_node(db_path, "ada", "Concept", "Python")
    _insert_edge(db_path, "ada", n1, n2, "KNOWS")

    result = get_graph_data(db_path)
    edge = result["edges"][0]

    assert "source" in edge
    assert "target" in edge
    assert "label" in edge


def test_node_label_prefers_first_name(tmp_path):
    """Person node with first_name uses it as label; falls back to name."""
    db_path = _make_test_db(str(tmp_path))
    _insert_node(db_path, "ada", "Person", "Daniel Stewart", first_name="Daniel")
    _insert_node(db_path, "ada", "Concept", "Python")

    result = get_graph_data(db_path)
    nodes_by_type = {n["type"]: n for n in result["nodes"]}

    assert nodes_by_type["Person"]["label"] == "Daniel"
    assert nodes_by_type["Concept"]["label"] == "Python"


def test_limits_to_400_nodes(tmp_path):
    """Inserts 500 nodes, asserts only 400 returned."""
    db_path = _make_test_db(str(tmp_path))
    conn = sqlite3.connect(db_path)
    for i in range(500):
        conn.execute(
            "INSERT INTO nodes (agent_id, type, name) VALUES (?, ?, ?)",
            ("ada", "Concept", f"node_{i}")
        )
    conn.commit()
    conn.close()

    result = get_graph_data(db_path)
    assert len(result["nodes"]) == 400


def test_filters_dangling_edges(tmp_path):
    """Edge referencing a node outside the 400 limit is excluded."""
    db_path = _make_test_db(str(tmp_path))
    conn = sqlite3.connect(db_path)
    # Insert 401 nodes; the last one will be outside the 400 limit
    for i in range(401):
        conn.execute(
            "INSERT INTO nodes (agent_id, type, name) VALUES (?, ?, ?)",
            ("ada", "Concept", f"node_{i}")
        )
    # Edge between node 1 and node 401 (the 401st node, which will be excluded)
    conn.execute(
        "INSERT INTO edges (agent_id, source_id, target_id, type) VALUES (?, ?, ?, ?)",
        ("ada", 1, 401, "RELATED_TO")
    )
    # Edge between node 1 and node 2 (both within 400 limit)
    conn.execute(
        "INSERT INTO edges (agent_id, source_id, target_id, type) VALUES (?, ?, ?, ?)",
        ("ada", 1, 2, "RELATED_TO")
    )
    conn.commit()
    conn.close()

    result = get_graph_data(db_path)
    assert len(result["nodes"]) == 400
    # Only the edge between nodes 1 and 2 should remain
    assert len(result["edges"]) == 1
    edge = result["edges"][0]
    assert str(edge["source"]) == "1"
    assert str(edge["target"]) == "2"


def test_empty_database_returns_empty_lists(tmp_path):
    """Empty nodes/edges when DB has no data."""
    db_path = _make_test_db(str(tmp_path))

    result = get_graph_data(db_path)

    assert result["nodes"] == []
    assert result["edges"] == []


def test_read_only_connection_rejects_writes(tmp_path):
    """Opening with ?mode=ro prevents INSERT."""
    db_path = _make_test_db(str(tmp_path))

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute(
            "INSERT INTO nodes (agent_id, type, name) VALUES (?, ?, ?)",
            ("ada", "Person", "Test")
        )
    conn.close()


def test_missing_db_file_returns_error(tmp_path):
    """Graceful error when DB path does not exist."""
    db_path = os.path.join(str(tmp_path), "nonexistent.db")

    result = get_graph_data(db_path)

    assert result["nodes"] == []
    assert result["edges"] == []
    assert "error" in result
