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
    assert set(body["checks"]) == {
        "database",
        "jobs",
        "llm_provider",
        "embedding_provider",
    }
    # The in-process job queue check never needs external services.
    assert body["checks"]["jobs"]["status"] == "ok"
    assert body["checks"]["jobs"]["backend"] == "inprocess"


def test_readiness_embedding_provider_flags_missing_key(monkeypatch):
    # Default Anthropic setup resolves embeddings to OpenAI; without an OpenAI
    # key the embedding provider must report an error (not silently pass).
    import app.config
    import app.llm.provider_registry as reg

    reg._instances.clear()
    monkeypatch.setattr(app.config.settings, "default_llm_provider", "anthropic")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resp = client.get("/api/v1/health/ready")
    checks = resp.json()["checks"]
    assert checks["embedding_provider"]["status"] == "error"
    assert resp.status_code == 503
    reg._instances.clear()


def test_readiness_embedding_provider_ok_with_key(monkeypatch):
    import app.config
    import app.llm.provider_registry as reg

    reg._instances.clear()
    monkeypatch.setattr(app.config.settings, "default_llm_provider", "anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")

    resp = client.get("/api/v1/health/ready")
    checks = resp.json()["checks"]
    assert checks["embedding_provider"]["status"] == "ok"
    assert checks["embedding_provider"]["provider"] == "openai"
    reg._instances.clear()


def test_request_id_header_propagated():
    resp = client.get("/api/v1/health/live")
    assert REQUEST_ID_HEADER in resp.headers

    supplied = "my-correlation-id"
    resp = client.get("/api/v1/health/live", headers={REQUEST_ID_HEADER: supplied})
    assert resp.headers[REQUEST_ID_HEADER] == supplied
