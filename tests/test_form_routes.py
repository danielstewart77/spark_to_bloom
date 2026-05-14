"""Tests for the KJ Dream Homes form intake endpoint."""

import json
import os
import sys
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as main_mod


@pytest.fixture(autouse=True)
def clear_form_rate_limit_state():
    main_mod._FORM_RATE_LIMIT_STATE.clear()
    yield
    main_mod._FORM_RATE_LIMIT_STATE.clear()


def test_kj_form_accepts_valid_api_key_and_persists_submission(tmp_path, monkeypatch):
    submissions_path = tmp_path / "form_submissions.jsonl"
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(submissions_path))
    client = TestClient(main_mod.app)

    response = client.post(
        "/api/forms/kj-dream-homes/contact",
        headers={
            "x-api-key": "test-form-key",
            "origin": "http://localhost:3000",
        },
        json={
            "form_name": "contact",
            "fields": {
                "name": "Casey Client",
                "email": "casey@example.com",
                "message": "Looking for a custom home quote.",
            },
            "meta": {
                "page_url": "http://localhost:3000/contact",
            },
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["submission_id"]

    saved_lines = submissions_path.read_text(encoding="utf-8").splitlines()
    assert len(saved_lines) == 1
    saved = json.loads(saved_lines[0])
    assert saved["site"] == "kj-dream-homes"
    assert saved["fields"]["email"] == "casey@example.com"
    assert saved["meta"]["page_url"] == "http://localhost:3000/contact"


def test_kj_form_rejects_invalid_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(tmp_path / "form_submissions.jsonl"))
    client = TestClient(main_mod.app)

    response = client.post(
        "/api/forms/kj-dream-homes/contact",
        headers={"x-api-key": "wrong-key"},
        json={"form_name": "contact", "fields": {"email": "casey@example.com"}},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_kj_form_rejects_disallowed_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_ALLOWED_ORIGINS", "https://kjdreamhomes.com")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(tmp_path / "form_submissions.jsonl"))
    client = TestClient(main_mod.app)

    response = client.post(
        "/api/forms/kj-dream-homes/contact",
        headers={
            "x-api-key": "test-form-key",
            "origin": "http://localhost:3000",
        },
        json={"form_name": "contact", "fields": {"email": "casey@example.com"}},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Origin not allowed"


def test_kj_form_requires_runtime_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("STB_FORM_API_KEY", raising=False)
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(tmp_path / "form_submissions.jsonl"))
    client = TestClient(main_mod.app)

    response = client.post(
        "/api/forms/kj-dream-homes/contact",
        json={"form_name": "contact", "fields": {"email": "casey@example.com"}},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Form intake is not configured"


def test_kj_form_honeypot_is_marked_as_spam_and_not_emailed(tmp_path, monkeypatch):
    submissions_path = tmp_path / "form_submissions.jsonl"
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(submissions_path))
    client = TestClient(main_mod.app)

    response = client.post(
        "/api/forms/kj-dream-homes/contact",
        headers={"x-api-key": "test-form-key"},
        json={
            "form_name": "buyer-intake",
            "fields": {
                "first_name": "Spam",
                "email": "spam@example.com",
                "company": "Bad Bot LLC",
            },
        },
    )

    assert response.status_code == 202
    saved = json.loads(submissions_path.read_text(encoding="utf-8").splitlines()[0])
    assert saved["spam_check"]["verdict"] == "spam"
    assert saved["delivery"]["status"] == "skipped_spam"


def test_kj_form_ham_submission_sends_email(tmp_path, monkeypatch):
    submissions_path = tmp_path / "form_submissions.jsonl"
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(submissions_path))
    client = TestClient(main_mod.app)

    with patch(
        "main._hive_tools_request_json",
        side_effect=[
            {"verdict": "ham", "confidence": 0.98, "reason": "Looks like a normal lead."},
            {"status": "sent"},
        ],
    ) as mock_hive_tools:
        response = client.post(
            "/api/forms/kj-dream-homes/contact",
            headers={"x-api-key": "test-form-key"},
            json={
                "form_name": "buyer-intake",
                "fields": {
                    "first_name": "Casey",
                    "last_name": "Client",
                    "email": "casey@example.com",
                },
            },
        )

    assert response.status_code == 202
    assert mock_hive_tools.call_count == 2
    saved = json.loads(submissions_path.read_text(encoding="utf-8").splitlines()[0])
    assert saved["spam_check"]["verdict"] == "ham"
    assert saved["delivery"]["status"] == "sent"


def test_kj_form_uncertain_submission_is_held_without_email(tmp_path, monkeypatch):
    submissions_path = tmp_path / "form_submissions.jsonl"
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(submissions_path))
    client = TestClient(main_mod.app)

    with patch(
        "main._hive_tools_request_json",
        return_value={"verdict": "uncertain", "confidence": 0.42, "reason": "Too little context."},
    ) as mock_hive_tools:
        response = client.post(
            "/api/forms/kj-dream-homes/contact",
            headers={"x-api-key": "test-form-key"},
            json={
                "form_name": "buyer-intake",
                "fields": {"email": "casey@example.com"},
            },
        )

    assert response.status_code == 202
    assert mock_hive_tools.call_count == 1
    saved = json.loads(submissions_path.read_text(encoding="utf-8").splitlines()[0])
    assert saved["spam_check"]["verdict"] == "uncertain"
    assert saved["delivery"]["status"] == "held_uncertain"


def test_kj_form_preflight_returns_cors_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(tmp_path / "form_submissions.jsonl"))
    client = TestClient(main_mod.app)

    response = client.options(
        "/api/forms/kj-dream-homes/contact",
        headers={
            "origin": "http://localhost:4321",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type,x-api-key",
        },
    )

    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://localhost:4321"
    assert response.headers["access-control-allow-methods"] == "POST, OPTIONS"
    assert response.headers["access-control-allow-headers"] == "content-type,x-api-key"


def test_kj_form_preflight_rejects_disallowed_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_ALLOWED_ORIGINS", "https://kjdreamhomes.com")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(tmp_path / "form_submissions.jsonl"))
    client = TestClient(main_mod.app)

    response = client.options(
        "/api/forms/kj-dream-homes/contact",
        headers={
            "origin": "http://localhost:4321",
            "access-control-request-method": "POST",
        },
    )

    assert response.status_code == 403


def test_kj_form_rate_limit_blocks_after_five_submissions(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_FORM_API_KEY", "test-form-key")
    monkeypatch.setenv("STB_FORM_SUBMISSIONS_PATH", str(tmp_path / "form_submissions.jsonl"))
    client = TestClient(main_mod.app)

    with patch(
        "main._classify_submission_spam",
        return_value={"verdict": "uncertain", "confidence": 0.0, "reason": "test", "source": "test"},
    ):
        for _ in range(5):
            response = client.post(
                "/api/forms/kj-dream-homes/contact",
                headers={"x-api-key": "test-form-key"},
                json={"form_name": "contact", "fields": {"email": "casey@example.com"}},
            )
            assert response.status_code == 202

        blocked = client.post(
            "/api/forms/kj-dream-homes/contact",
            headers={"x-api-key": "test-form-key"},
            json={"form_name": "contact", "fields": {"email": "casey@example.com"}},
        )

    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many submissions"
