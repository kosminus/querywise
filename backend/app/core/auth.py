"""Request-level authentication & authorization.

Provides the FastAPI dependencies that the API and service layers build on:

* :func:`get_current_user`  — resolves the caller (session cookie, Bearer JWT,
  or ``X-API-Key``) to a :class:`User`, or 401.
* :func:`get_org_context`   — resolves the active workspace + role into an
  :class:`AuthContext` (the object threaded into services for scoping).
* :func:`require_role`       — dependency factory enforcing a minimum role.

``DISABLE_AUTH=true`` short-circuits authentication to the bootstrapped default
admin for local development. Never enable it in production.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import (
    TOKEN_PURPOSE_SESSION,
    decode_token,
    hash_api_key,
)
from app.db.models.api_key import ApiKey
from app.db.models.membership import ROLE_RANK, Membership
from app.db.models.user import User
from app.db.session import get_db


@dataclass
class AuthContext:
    """The authenticated caller plus their active workspace + role.

    Threaded into service functions so they can scope queries by
    ``organization_id`` / ``workspace_id`` and enforce role checks.
    """

    user: User
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    role: str

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def has_role(self, minimum: str) -> bool:
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK.get(minimum, 99)

    def require_role(self, minimum: str) -> None:
        if not self.has_role(minimum):
            raise AuthorizationError(f"This action requires the '{minimum}' role.")


# --- Cookie helpers ---------------------------------------------------------


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session JWT as an HTTP-only cookie."""
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.jwt_access_ttl_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=cast(Literal["lax", "strict", "none"], settings.auth_cookie_samesite),
        domain=settings.auth_cookie_domain,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        domain=settings.auth_cookie_domain,
        path="/",
    )


# --- Authentication ---------------------------------------------------------


async def _user_from_api_key(db: AsyncSession, raw_key: str) -> User:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.key_hash == hash_api_key(raw_key))
        .options(selectinload(ApiKey.user))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None or api_key.revoked_at is not None:
        raise AuthenticationError("Invalid API key")
    now = datetime.now(UTC)
    if api_key.expires_at is not None and api_key.expires_at < now:
        raise AuthenticationError("API key expired")
    if api_key.user is None or not api_key.user.is_active:
        raise AuthenticationError("API key owner is inactive")
    api_key.last_used_at = now
    return api_key.user


def _extract_bearer_or_cookie(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.cookies.get(settings.auth_cookie_name)


async def _dev_admin(db: AsyncSession) -> User:
    """Load the bootstrapped default admin for DISABLE_AUTH local dev."""
    result = await db.execute(select(User).where(User.email == settings.default_admin_email))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError(
            "DISABLE_AUTH is set but the default admin "
            f"({settings.default_admin_email}) does not exist. Run migrations / boot once."
        )
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the calling user from API key, Bearer token, or session cookie."""
    if settings.disable_auth:
        return await _dev_admin(db)

    api_key = request.headers.get("x-api-key")
    if api_key:
        return await _user_from_api_key(db, api_key)

    token = _extract_bearer_or_cookie(request)
    if not token:
        raise AuthenticationError()

    payload = decode_token(token, TOKEN_PURPOSE_SESSION)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Malformed token subject") from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return user


# --- Authorization (workspace + role) ---------------------------------------


async def get_org_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Resolve the active workspace + role for the caller.

    The active workspace is chosen from the ``X-Workspace-Id`` header when the
    user is a member of it; otherwise the earliest-joined membership is used.
    """
    result = await db.execute(
        select(Membership)
        .where(Membership.user_id == user.id)
        .options(selectinload(Membership.team))
        .order_by(Membership.created_at)
    )
    memberships = list(result.scalars().all())
    if not memberships:
        raise AuthorizationError("User is not a member of any workspace.")

    selected = memberships[0]
    requested = request.headers.get("x-workspace-id")
    if requested:
        try:
            requested_id = uuid.UUID(requested)
        except ValueError as exc:
            raise AuthorizationError("Invalid X-Workspace-Id header.") from exc
        match = next((m for m in memberships if m.team_id == requested_id), None)
        if match is None:
            raise AuthorizationError("You are not a member of the requested workspace.")
        selected = match

    return AuthContext(
        user=user,
        organization_id=selected.team.organization_id,
        workspace_id=selected.team_id,
        role=selected.role,
    )


def require_role(minimum: str):
    """Dependency factory: require at least ``minimum`` role in the workspace."""

    async def _dependency(ctx: AuthContext = Depends(get_org_context)) -> AuthContext:
        ctx.require_role(minimum)
        return ctx

    return _dependency
