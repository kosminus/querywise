"""Endpoint-level auth tests via TestClient.

Like test_health, these do NOT enter the lifespan (no DB setup). They assert
that protected routes reject unauthenticated callers *before* any DB access,
and that the public provider-discovery endpoint works.
"""

import pytest
from fastapi.testclient import TestClient

from app.core import auth as auth_module
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth_enabled(monkeypatch):
    # Ensure the dev escape hatch is off so auth is actually enforced.
    monkeypatch.setattr(auth_module.settings, "disable_auth", False)
    yield


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/connections"),
        ("post", "/api/v1/connections"),
        ("get", "/api/v1/teams"),
        ("get", "/api/v1/api-keys"),
        ("get", "/api/v1/auth/me"),
    ],
)
def test_protected_routes_require_auth(method, path):
    kwargs = {"json": {}} if method == "post" else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 401
    assert "error" in resp.json()


def test_bad_bearer_token_rejected():
    resp = client.get(
        "/api/v1/connections", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert resp.status_code == 401


def test_auth_providers_is_public():
    resp = client.get("/api/v1/auth/providers")
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body
    assert {"supports_password", "supports_magic_link", "is_sso", "disable_auth"} <= body.keys()
