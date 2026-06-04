import pytest

from app.core import secrets
from app.core.secrets import (
    FernetSecretsProvider,
    SecretsProvider,
    get_secrets_provider,
    register_secrets_backend,
    reset_secrets_provider,
)


def test_fernet_roundtrip():
    provider = FernetSecretsProvider()
    token = provider.encrypt("postgresql://u:p@host:5432/db")
    assert token != "postgresql://u:p@host:5432/db"
    assert provider.decrypt(token) == "postgresql://u:p@host:5432/db"


def test_fernet_is_deterministic_key_not_ciphertext():
    # Same passphrase decrypts the other instance's ciphertext (stable key)...
    a = FernetSecretsProvider(key="shared-key")
    b = FernetSecretsProvider(key="shared-key")
    token = a.encrypt("secret")
    assert b.decrypt(token) == "secret"


def test_default_backend_is_env():
    provider = get_secrets_provider()
    assert provider.backend_name == "env"
    assert isinstance(provider, FernetSecretsProvider)


def test_unknown_backend_raises(monkeypatch):
    reset_secrets_provider()
    monkeypatch.setattr(secrets.settings, "secrets_backend", "does-not-exist")
    with pytest.raises(ValueError, match="Unknown secrets backend"):
        get_secrets_provider()


def test_unimplemented_cloud_backend_raises(monkeypatch):
    reset_secrets_provider()
    monkeypatch.setattr(secrets.settings, "secrets_backend", "aws")
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        get_secrets_provider()


def test_register_custom_backend(monkeypatch):
    class PlainProvider(SecretsProvider):
        backend_name = "plain"

        def encrypt(self, plaintext: str) -> str:
            return f"plain:{plaintext}"

        def decrypt(self, ciphertext: str) -> str:
            return ciphertext.removeprefix("plain:")

    register_secrets_backend("plain", PlainProvider)
    reset_secrets_provider()
    monkeypatch.setattr(secrets.settings, "secrets_backend", "plain")
    provider = get_secrets_provider()
    assert provider.encrypt("x") == "plain:x"
    assert provider.decrypt("plain:x") == "x"
