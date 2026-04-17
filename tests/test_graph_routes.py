"""API tests for /graph and /graph/data endpoints."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as main_mod
from starlette.testclient import TestClient

_SAMPLE = {
    "nodes": [
        {"id": "1", "label": "Daniel", "type": "Person", "properties": {}},
        {"id": "2", "label": "Python", "type": "Concept", "properties": {}},
    ],
    "edges": [
        {"source": "1", "target": "2", "label": "KNOWS"},
    ],
}

_EMPTY = {"nodes": [], "edges": []}
_ERROR = {"nodes": [], "edges": [], "error": "connection refused"}


@pytest.fixture()
def client():
    return TestClient(main_mod.app)


def test_graph_data_returns_json(client):
    """GET /graph/data returns 200 with JSON body containing 'nodes' and 'edges'."""
    with patch("main.get_graph_data", return_value=_SAMPLE):
        resp = client.get("/graph/data")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1


def test_graph_data_forwards_limit_param(client):
    """limit query param is forwarded to get_graph_data."""
    with patch("main.get_graph_data", return_value=_EMPTY) as mock_fn:
        client.get("/graph/data?limit=50")
    mock_fn.assert_called_once_with(main_mod.GRAPH_API_URL, limit=50)


def test_graph_data_default_limit(client):
    """Default limit of 400 is used when not specified."""
    with patch("main.get_graph_data", return_value=_EMPTY) as mock_fn:
        client.get("/graph/data")
    mock_fn.assert_called_once_with(main_mod.GRAPH_API_URL, limit=400)


def test_graph_data_propagates_upstream_error(client):
    """When upstream returns error dict, endpoint still returns 200 with empty lists."""
    with patch("main.get_graph_data", return_value=_ERROR):
        resp = client.get("/graph/data")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"] == []
    assert data["edges"] == []


def test_graph_page_returns_html(client):
    """GET /graph returns 200 with HTML content type."""
    resp = client.get("/graph")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_graph_page_contains_cytoscape_reference(client):
    """GET /graph response body contains 'cytoscape' (CDN script tag)."""
    resp = client.get("/graph")
    assert "cytoscape" in resp.text.lower()
