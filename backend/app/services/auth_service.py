"""Interactive authentication flows: password login and magic-link.

The configured :mod:`app.core.auth_providers` advertises which of these a
deployment exposes; the actual credential handling lives here. New users
discovered via magic-link are auto-provisioned into the default workspace as
viewers (first-run, single-company convenience).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ValidationError
from app.core.security import (
    TOKEN_PURPOSE_MAGIC_LINK,
    create_magic_link_token,
    create_session_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.membership import ROLE_VIEWER, Membership
from app.db.models.user import User
from app.services import identity_service


def _normalize_email(email: str) -> str:
    return email.lower().strip()


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == _normalize_email(email)))
    return result.scalar_one_or_none()


async def _ensure_default_membership(db: AsyncSession, user: User) -> None:
    """Give a freshly provisioned user viewer access to the default workspace."""
    org, team, _admin = await identity_service.bootstrap_default_identity(db)
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.team_id == team.id
        )
    )
    if result.scalar_one_or_none() is None:
        db.add(Membership(user_id=user.id, team_id=team.id, role=ROLE_VIEWER))
        await db.flush()


async def find_or_create_user(
    db: AsyncSession,
    email: str,
    name: str | None = None,
    sso_subject: str | None = None,
) -> User:
    user = await _get_user_by_email(db, email)
    if user is None:
        user = User(email=_normalize_email(email), name=name, sso_subject=sso_subject)
        db.add(user)
        await db.flush()
        await _ensure_default_membership(db, user)
    return user


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    name: str | None = None,
) -> User:
    """Create a local password account and provision default access."""
    if await _get_user_by_email(db, email) is not None:
        raise ValidationError("A user with this email already exists.")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    user = User(
        email=_normalize_email(email),
        name=name,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    await _ensure_default_membership(db, user)
    return user


async def authenticate_password(db: AsyncSession, email: str, password: str) -> User:
    user = await _get_user_by_email(db, email)
    # Verify even when the user is missing to avoid timing-based enumeration.
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")
    await _touch_login(db, user)
    return user


async def request_magic_link(db: AsyncSession, email: str) -> str:
    """Issue a magic-link token for ``email``.

    Returns the signed token; delivery (email/Slack) is the caller's concern.
    For local dev the token is surfaced directly by the endpoint.
    """
    return create_magic_link_token(_normalize_email(email))


async def verify_magic_link(db: AsyncSession, token: str) -> User:
    payload = decode_token(token, TOKEN_PURPOSE_MAGIC_LINK)
    email = payload.get("sub")
    if not email:
        raise AuthenticationError("Malformed magic-link token.")
    user = await find_or_create_user(db, email)
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")
    await _touch_login(db, user)
    return user


async def _touch_login(db: AsyncSession, user: User) -> None:
    user.last_login_at = datetime.now(UTC)
    await db.flush()


def issue_session_token(user: User) -> str:
    return create_session_token(str(user.id))
