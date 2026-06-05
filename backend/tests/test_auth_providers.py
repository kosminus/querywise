"""Unit tests for the pluggable auth-provider registry and AuthContext roles."""

import uuid

import pytest

from app.core import auth_providers
from app.core.auth import AuthContext
from app.core.auth_providers import (
    AuthProvider,
    LocalAuthProvider,
    OIDCAuthProvider,
    get_auth_provider,
    register_auth_provider,
    reset_auth_provider,
)
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from app.db.models.user import User


@pytest.fixture(autouse=True)
def _reset_provider():
    reset_auth_provider()
    yield
    reset_auth_provider()


def test_default_provider_is_local(monkeypatch):
    monkeypatch.setattr(auth_providers.settings, "auth_provider", "local")
    provider = get_auth_provider()
    assert isinstance(provider, LocalAuthProvider)
    assert provider.supports_password
    assert provider.supports_magic_link


def test_describe_shape(monkeypatch):
    monkeypatch.setattr(auth_providers.settings, "auth_provider", "magic_link")
    info = get_auth_provider().describe()
    assert info == {
        "name": "magic_link",
        "supports_password": False,
        "supports_magic_link": True,
        "is_sso": False,
    }


def test_oidc_is_an_unimplemented_seam():
    provider = OIDCAuthProvider()
    assert provider.is_sso
    with pytest.raises(NotImplementedError):
        provider.authorization_url("state")


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(auth_providers.settings, "auth_provider", "nope")
    with pytest.raises(ValueError):
        get_auth_provider()


def test_register_custom_provider(monkeypatch):
    class CustomSSO(AuthProvider):
        name = "custom"
        is_sso = True

    register_auth_provider("custom", CustomSSO)
    monkeypatch.setattr(auth_providers.settings, "auth_provider", "custom")
    assert isinstance(get_auth_provider(), CustomSSO)


# --- AuthContext role logic -------------------------------------------------


def _ctx(role: str) -> AuthContext:
    return AuthContext(
        user=User(id=uuid.uuid4(), email="x@y.z"),
        organization_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        role=role,
    )


def test_role_hierarchy():
    admin = _ctx(ROLE_ADMIN)
    editor = _ctx(ROLE_EDITOR)
    viewer = _ctx(ROLE_VIEWER)

    assert admin.has_role(ROLE_EDITOR) and admin.has_role(ROLE_VIEWER)
    assert editor.has_role(ROLE_EDITOR) and not editor.has_role(ROLE_ADMIN)
    assert viewer.has_role(ROLE_VIEWER) and not viewer.has_role(ROLE_EDITOR)


def test_require_role_raises_for_insufficient():
    from app.core.exceptions import AuthorizationError

    viewer = _ctx(ROLE_VIEWER)
    with pytest.raises(AuthorizationError):
        viewer.require_role(ROLE_EDITOR)
    # Sufficient role does not raise.
    viewer.require_role(ROLE_VIEWER)
