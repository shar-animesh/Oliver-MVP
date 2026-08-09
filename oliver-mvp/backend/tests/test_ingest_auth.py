"""
Auth coverage for the machine ingestion endpoint (Power Automate -> /ingest/email).

Run from the backend/ directory:
    pip install -e ../packages/oliver-core fastapi httpx pytest
    python -m pytest tests/ -q

require_ingest_client reads OLIVER_REQUIRE_AUTH / OLIVER_INGEST_TOKEN per request,
so a single TestClient is enough; we just toggle env between assertions.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

EMAIL = {
    "message_id": "pytest-auth",
    "subject": "Predictive maintenance pilot",
    "body": (
        "Unplanned turbine downtime costs ~2M EUR/year; we want 48-hour failure "
        "warnings from vibration data. Sponsor: VP Gas Services."
    ),
}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _email(mid: str) -> dict:
    return {**EMAIL, "message_id": mid}


def test_local_dev_no_token_required(monkeypatch, client):
    monkeypatch.delenv("OLIVER_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("OLIVER_INGEST_TOKEN", raising=False)
    assert client.post("/api/v1/ingest/email", json=_email("dev")).status_code == 201


def test_health_never_requires_auth(monkeypatch, client):
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OLIVER_INGEST_TOKEN", "t0ken")
    assert client.get("/health").status_code == 200


def test_enforced_missing_token_rejected(monkeypatch, client):
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OLIVER_INGEST_TOKEN", "t0ken")
    assert client.post("/api/v1/ingest/email", json=_email("miss")).status_code == 401


def test_enforced_wrong_token_rejected(monkeypatch, client):
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OLIVER_INGEST_TOKEN", "t0ken")
    r = client.post("/api/v1/ingest/email", json=_email("wrong"),
                    headers={"Authorization": "Bearer NOPE"})
    assert r.status_code == 401


def test_enforced_actor_stand_in_does_not_open_ingest(monkeypatch, client):
    # The human-attribution 'actor:' stand-in must never satisfy the machine gate.
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OLIVER_INGEST_TOKEN", "t0ken")
    r = client.post("/api/v1/ingest/email", json=_email("actor"),
                    headers={"Authorization": "Bearer actor:animesh"})
    assert r.status_code == 401


def test_enforced_x_actor_header_does_not_bypass(monkeypatch, client):
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OLIVER_INGEST_TOKEN", "t0ken")
    r = client.post("/api/v1/ingest/email", json=_email("xactor"),
                    headers={"X-Oliver-Actor": "animesh"})
    assert r.status_code == 401


def test_enforced_correct_token_accepted(monkeypatch, client):
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OLIVER_INGEST_TOKEN", "t0ken")
    r = client.post("/api/v1/ingest/email", json=_email("ok"),
                    headers={"Authorization": "Bearer t0ken"})
    assert r.status_code == 201


def test_enforced_but_unconfigured_fails_closed(monkeypatch, client):
    # Enforcement on but no secret set is a deploy error -> 500, never an open door.
    monkeypatch.setenv("OLIVER_REQUIRE_AUTH", "true")
    monkeypatch.delenv("OLIVER_INGEST_TOKEN", raising=False)
    assert client.post("/api/v1/ingest/email", json=_email("misconf")).status_code == 500
