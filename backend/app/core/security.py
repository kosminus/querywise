"""Low-level auth primitives: password hashing, JWTs, and API keys.

Kept dependency-light and free of FastAPI/DB imports so it is trivially unit
testable. Higher-level request plumbing (dependencies, cookies, AuthContext)
lives in :mod:`app.core.auth`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings
from app.core.exceptions import AuthenticationError

# --- Passwords (PBKDF2-HMAC-SHA256, stdlib — no native build deps) ----------

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ROUNDS = 390_000


def hash_password(password: str) -> str:
    """Return an encoded ``algo$rounds$salt$hash`` string for ``password``."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-time check of ``password`` against an encoded hash."""
    if not encoded:
        return False
    try:
        algo, rounds_s, salt_hex, hash_hex = encoded.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return hmac.compare_digest(digest, expected)


# --- JWTs (HS256, stateless sessions + magic-link tokens) -------------------

TOKEN_PURPOSE_SESSION = "session"
TOKEN_PURPOSE_MAGIC_LINK = "magic_link"


def create_token(
    subject: str,
    purpose: str,
    ttl_minutes: int,
    **extra_claims: Any,
) -> str:
    """Sign a JWT for ``subject`` with a ``purpose`` claim and TTL."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        **extra_claims,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_purpose: str) -> dict[str, Any]:
    """Decode and validate a JWT, enforcing signature, expiry, and purpose."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc
    if payload.get("purpose") != expected_purpose:
        raise AuthenticationError("Token purpose mismatch")
    return payload


def create_session_token(user_id: str) -> str:
    return create_token(user_id, TOKEN_PURPOSE_SESSION, settings.jwt_access_ttl_minutes)


def create_magic_link_token(email: str) -> str:
    # Magic-link subject is the email — the user may not exist yet at request time.
    return create_token(email, TOKEN_PURPOSE_MAGIC_LINK, settings.magic_link_ttl_minutes)


# --- API keys ---------------------------------------------------------------

API_KEY_PREFIX = "qw_"


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(plaintext, sha256_hash, display_prefix)`` for a new API key.

    The plaintext is shown to the user exactly once; only the hash is stored.
    """
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, hash_api_key(plaintext), plaintext[:10]


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()
