"""Route tests for the BTC accumulation tracker dashboard."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auth
import main as main_mod


def _authed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    monkeypatch.setenv("BTC_LEDGER_API_TOKEN", "test-token-abc")
    monkeypatch.setenv("BTC_LEDGER_URL", "http://btc-ledger-test:8427")
    user = auth.create_user("daniel", "secret-pass", is_admin=True, replace=True)
    client = TestClient(main_mod.app)
    client.cookies.set(auth.SESSION_COOKIE_NAME, auth.create_session_token(user))
    return client


def test_btc_page_redirects_when_unauthenticated(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/btc", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=/btc")


def test_btc_page_renders_for_authed_user(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)

    response = client.get("/btc")

    assert response.status_code == 200
    assert "bitcoin accumulation tracker" in response.text


def test_api_btc_stats_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/api/btc/stats")

    assert response.status_code == 401


def test_api_btc_latest_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/api/btc/latest")

    assert response.status_code == 401


def test_api_btc_observations_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/api/btc/observations")

    assert response.status_code == 401


def test_api_btc_alerts_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/api/btc/alerts")

    assert response.status_code == 401


def test_api_btc_stats_proxies_ledger(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    fake_stats = {
        "total_invested_usd": 1200.0,
        "total_btc": 0.02,
        "average_cost_basis_usd": 60000.0,
        "purchase_count": 8,
        "first_purchase_ts": 1700000000,
        "last_purchase_ts": 1750000000,
        "alert_count": 5,
        "observation_count": 720,
    }

    with patch.object(main_mod, "_btc_ledger_get", new=AsyncMock(return_value=fake_stats)):
        response = client.get("/api/btc/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["total_invested_usd"] == 1200.0
    assert data["alert_count"] == 5


def test_api_btc_latest_proxies_ledger(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    fake_obs = {
        "id": 1,
        "timestamp": 1750000000,
        "price_usd": 65000.0,
        "ath_usd": 73000.0,
        "drawdown_pct": 11.0,
        "ma_200d": 60000.0,
        "mayer_multiple": 1.08,
        "fear_greed": 45,
        "fear_greed_classification": "Neutral",
        "source": "live",
    }

    with patch.object(main_mod, "_btc_ledger_get", new=AsyncMock(return_value=fake_obs)):
        response = client.get("/api/btc/latest")

    assert response.status_code == 200
    data = response.json()
    assert data["price_usd"] == 65000.0


def test_api_btc_observations_proxies_ledger(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    fake_obs = [{"id": 1, "timestamp": 1750000000, "price_usd": 65000.0, "source": "live"}]

    with patch.object(main_mod, "_btc_ledger_get", new=AsyncMock(return_value=fake_obs)):
        response = client.get("/api/btc/observations?days=30")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_btc_alerts_proxies_ledger(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    fake_alerts = [
        {
            "id": 1,
            "timestamp": 1750000000,
            "tier": "opportunistic",
            "previous_tier": "none",
            "price_usd": 62000.0,
            "mayer_multiple": 0.95,
            "drawdown_pct": 30.0,
            "fear_greed": 22,
            "signals_active": ["mayer", "drawdown"],
            "suggested_buy_usd": 150.0,
            "alert_reason": "escalation",
            "delivered": True,
            "delivered_at": None,
        }
    ]

    with patch.object(main_mod, "_btc_ledger_get", new=AsyncMock(return_value=fake_alerts)):
        response = client.get("/api/btc/alerts")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["tier"] == "opportunistic"


def test_api_btc_purchases_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_DB_PATH", str(tmp_path / "stb.db"))
    monkeypatch.setenv("STB_SECRET_KEY", "test-secret")
    client = TestClient(main_mod.app)

    response = client.get("/api/btc/purchases")

    assert response.status_code == 401


def test_api_btc_purchases_proxies_ledger(tmp_path, monkeypatch):
    client = _authed_client(tmp_path, monkeypatch)
    fake_purchases = [
        {
            "id": 1,
            "timestamp": 1750000000,
            "amount_usd": 500.0,
            "btc_amount": 0.008,
            "price_per_btc_usd": 62500.0,
            "fees_usd": 8.0,
            "source": "coinbase_import",
            "exchange": "Coinbase",
            "transaction_id": "abc123",
            "alert_id": None,
            "notes": "Buy",
        }
    ]

    with patch.object(main_mod, "_btc_ledger_get", new=AsyncMock(return_value=fake_purchases)):
        response = client.get("/api/btc/purchases?days=365")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["price_per_btc_usd"] == 62500.0
