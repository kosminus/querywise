"""Unit tests for the auth primitives (passwords, JWTs, API keys).

No DB or network — pure crypto/token logic.
"""

import time

import jwt
import pytest

from app.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    TOKEN_PURPOSE_MAGIC_LINK,
    TOKEN_PURPOSE_SESSION,
    API_KEY_PREFIX,
    create_session_token,
    create_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


# --- Passwords --------------------------------------------------------------


def test_password_roundtrip():
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)


def test_password_wrong_rejected():
    encoded = hash_password("s3cret-value")
    assert not verify_password("wrong-value", encoded)


def test_password_salt_is_random():
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize("bad", [None, "", "not-the-format", "pbkdf2_sha256$abc"])
def test_verify_handles_malformed(bad):
    assert verify_password("whatever", bad) is False


# --- JWTs -------------------------------------------------------------------


def test_session_token_roundtrip():
    token = create_session_token("user-123")
    payload = decode_token(token, TOKEN_PURPOSE_SESSION)
    assert payload["sub"] == "user-123"
    assert payload["purpose"] == TOKEN_PURPOSE_SESSION


def test_purpose_mismatch_rejected():
    token = create_session_token("user-123")
    with pytest.raises(AuthenticationError):
        decode_token(token, TOKEN_PURPOSE_MAGIC_LINK)


def test_bad_signature_rejected():
    token = create_session_token("user-123")
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    with pytest.raises(AuthenticationError):
        decode_token(tampered, TOKEN_PURPOSE_SESSION)


def test_expired_token_rejected():
    token = create_token("user-123", TOKEN_PURPOSE_SESSION, ttl_minutes=0)
    time.sleep(1)
    with pytest.raises(AuthenticationError):
        decode_token(token, TOKEN_PURPOSE_SESSION)


def test_wrong_secret_rejected():
    token = jwt.encode(
        {"sub": "x", "purpose": TOKEN_PURPOSE_SESSION}, "some-other-secret", algorithm="HS256"
    )
    with pytest.raises(AuthenticationError):
        decode_token(token, TOKEN_PURPOSE_SESSION)


def test_signed_with_configured_secret():
    token = create_session_token("user-123")
    # Decodable with the configured secret directly.
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == "user-123"


# --- API keys ---------------------------------------------------------------


def test_api_key_generation():
    plaintext, key_hash, prefix = generate_api_key()
    assert plaintext.startswith(API_KEY_PREFIX)
    assert hash_api_key(plaintext) == key_hash
    assert prefix == plaintext[:10]
    assert len(key_hash) == 64  # sha256 hex


def test_api_keys_are_unique():
    a, _, _ = generate_api_key()
    b, _, _ = generate_api_key()
    assert a != b
