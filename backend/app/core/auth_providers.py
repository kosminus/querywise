"""Pluggable interactive-login backends.

Mirrors :mod:`app.core.secrets`: a small ``AuthProvider`` interface behind a
name-keyed registry so a deployment selects its login method with
``AUTH_PROVIDER`` and SSO backends can be registered without touching the core.

* ``local``      — email + password *and* magic-link (default; fully implemented
                   in :mod:`app.services.auth_service`).
* ``magic_link`` — passwordless email magic-link only.
* ``oidc``       — registered seam for OIDC/OAuth2 (Google/Okta/Entra). Not yet
                   implemented; ``authorization_url`` / ``exchange_code`` raise
                   until an implementation is registered via
                   :func:`register_auth_provider`.

The password / magic-link flows are driven by the service layer; this seam
exists so the configured provider advertises its capabilities to the frontend
(:func:`AuthProvider.describe`) and so SSO can slot in later.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import settings


@dataclass
class VerifiedIdentity:
    """An identity verified by a provider (e.g. after an SSO code exchange)."""

    email: str
    name: str | None = None
    sso_subject: str | None = None


class AuthProvider:
    """Base class for login backends. Subclasses set capability flags and, for
    SSO, override :meth:`authorization_url` / :meth:`exchange_code`."""

    name: str = "base"
    supports_password: bool = False
    supports_magic_link: bool = False
    is_sso: bool = False

    def authorization_url(self, state: str) -> str:
        """Return the IdP URL to redirect the browser to (SSO providers)."""
        raise NotImplementedError(f"Auth provider '{self.name}' does not support SSO redirects.")

    async def exchange_code(self, code: str, state: str | None = None) -> VerifiedIdentity:
        """Exchange an SSO authorization code for a verified identity."""
        raise NotImplementedError(f"Auth provider '{self.name}' does not support code exchange.")

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "supports_password": self.supports_password,
            "supports_magic_link": self.supports_magic_link,
            "is_sso": self.is_sso,
        }


class LocalAuthProvider(AuthProvider):
    """Self-hosted accounts — password login plus magic-link as a fallback."""

    name = "local"
    supports_password = True
    supports_magic_link = True


class MagicLinkAuthProvider(AuthProvider):
    """Passwordless email magic-link only (lowest-friction first-run)."""

    name = "magic_link"
    supports_magic_link = True


class OIDCAuthProvider(AuthProvider):
    """Seam for OIDC/OAuth2 SSO. Implementation deferred (Phase 1 follow-up)."""

    name = "oidc"
    is_sso = True

    def _unimplemented(self) -> NotImplementedError:
        return NotImplementedError(
            "OIDC auth is not yet implemented. Configure AUTH_PROVIDER=local or "
            "magic_link, or register an implementation with "
            "register_auth_provider('oidc', factory)."
        )

    def authorization_url(self, state: str) -> str:
        raise self._unimplemented()

    async def exchange_code(self, code: str, state: str | None = None) -> VerifiedIdentity:
        raise self._unimplemented()


_PROVIDER_FACTORIES: dict[str, Callable[[], AuthProvider]] = {
    "local": LocalAuthProvider,
    "magic_link": MagicLinkAuthProvider,
    "oidc": OIDCAuthProvider,
}

_instance: AuthProvider | None = None


def register_auth_provider(name: str, factory: Callable[[], AuthProvider]) -> None:
    """Register (or override) an auth provider factory by name."""
    global _instance
    _PROVIDER_FACTORIES[name] = factory
    _instance = None


def get_auth_provider() -> AuthProvider:
    """Return the process-wide provider for the configured ``AUTH_PROVIDER``."""
    global _instance
    if _instance is None:
        factory = _PROVIDER_FACTORIES.get(settings.auth_provider)
        if factory is None:
            raise ValueError(
                f"Unknown auth provider '{settings.auth_provider}'. "
                f"Available: {sorted(_PROVIDER_FACTORIES)}"
            )
        _instance = factory()
    return _instance


def reset_auth_provider() -> None:
    """Clear the cached provider. Test/reconfiguration hook."""
    global _instance
    _instance = None
