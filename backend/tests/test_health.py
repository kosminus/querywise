"""Health probe tests.

These hit the real ASGI app via TestClient but do NOT enter the lifespan
context (no startup hooks / DB setup run). The readiness probe therefore reports
the database as unavailable in CI, which is the behaviour we assert.
"""

from fastapi.testclient import TestClient

from app.core.telemetry import REQUEST_ID_HEADER
from app.main import app

client = TestClient(app)


def test_liveness_ok():
    resp = client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_legacy_health_ok():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_reports_components():
    resp = client.get("/api/v1/health/ready")
    # 200 if a DB happens to be reachable, 503 otherwise — both are valid.
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "checks" in body
    assert set(body["checks"]) == {"database", "jobs", "llm_provider"}
    # The job queue check never needs external services.
    assert body["checks"]["jobs"]["status"] == "ok"
    assert body["checks"]["jobs"]["backend"] == "inprocess"


def test_request_id_header_propagated():
    resp = client.get("/api/v1/health/live")
    assert REQUEST_ID_HEADER in resp.headers

    supplied = "my-correlation-id"
    resp = client.get("/api/v1/health/live", headers={REQUEST_ID_HEADER: supplied})
    assert resp.headers[REQUEST_ID_HEADER] == supplied
