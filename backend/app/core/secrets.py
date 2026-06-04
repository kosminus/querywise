"""Pluggable secrets backend for encrypting sensitive values at rest.

QueryWise stores warehouse connection strings encrypted in the app database.
This module abstracts *how* that encryption happens behind a small
``SecretsProvider`` interface so a deployment can keep the master key wherever
its compliance story requires:

* ``env``  — default. Derives a Fernet key from ``settings.encryption_key``.
             Preserves QueryWise's original behaviour exactly.
* ``aws``/``gcp``/``azure``/``vault`` — seams for AWS Secrets Manager, GCP
             Secret Manager, Azure Key Vault and HashiCorp Vault. Register an
             implementation via :func:`register_secrets_backend`.

The default is intentionally dependency-free; cloud backends pull in their own
SDKs only when selected.
"""

from __future__ import annotations

import base64
import hashlib
from abc import ABC, abstractmethod
from collections.abc import Callable

from cryptography.fernet import Fernet

from app.config import settings


class SecretsProvider(ABC):
    """Encrypts and decrypts sensitive values (e.g. connection strings)."""

    backend_name: str = "base"

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Return an opaque, storable ciphertext for ``plaintext``."""

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Return the plaintext for a value previously produced by ``encrypt``."""


class FernetSecretsProvider(SecretsProvider):
    """Symmetric encryption using a Fernet key derived from a passphrase.

    The key is the SHA-256 digest of ``settings.encryption_key`` (or an
    explicitly supplied key), base64-url encoded as Fernet requires.
    """

    backend_name = "env"

    def __init__(self, key: str | None = None) -> None:
        passphrase = key if key is not None else settings.encryption_key
        key_bytes = hashlib.sha256(passphrase.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()


def _build_env() -> SecretsProvider:
    return FernetSecretsProvider()


def _unimplemented(name: str) -> Callable[[], SecretsProvider]:
    def _factory() -> SecretsProvider:
        raise NotImplementedError(
            f"Secrets backend '{name}' is not yet implemented. "
            f"Set SECRETS_BACKEND=env, or register one with "
            f"register_secrets_backend('{name}', factory)."
        )

    return _factory


_BACKEND_FACTORIES: dict[str, Callable[[], SecretsProvider]] = {
    "env": _build_env,
    "aws": _unimplemented("aws"),
    "gcp": _unimplemented("gcp"),
    "azure": _unimplemented("azure"),
    "vault": _unimplemented("vault"),
}

_instance: SecretsProvider | None = None


def register_secrets_backend(name: str, factory: Callable[[], SecretsProvider]) -> None:
    """Register (or override) a secrets backend factory by name."""
    _BACKEND_FACTORIES[name] = factory


def get_secrets_provider() -> SecretsProvider:
    """Return the process-wide secrets provider for the configured backend."""
    global _instance
    if _instance is None:
        factory = _BACKEND_FACTORIES.get(settings.secrets_backend)
        if factory is None:
            raise ValueError(
                f"Unknown secrets backend '{settings.secrets_backend}'. "
                f"Available: {sorted(_BACKEND_FACTORIES)}"
            )
        _instance = factory()
    return _instance


def reset_secrets_provider() -> None:
    """Clear the cached provider. Primarily a test/reconfiguration hook."""
    global _instance
    _instance = None
