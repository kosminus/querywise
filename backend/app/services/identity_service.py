"""Organizations, teams (workspaces), memberships, and API keys.

Also owns identity bootstrap — ensuring the default org/workspace/admin exist —
which runs both in migration 004 (for existing deployments) and on every boot
(idempotent, for fresh databases).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import generate_api_key, hash_password
from app.db.models.api_key import ApiKey
from app.db.models.membership import ROLE_ADMIN, ROLES, Membership
from app.db.models.organization import Organization
from app.db.models.team import Team
from app.db.models.user import User


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "team"


# --- Bootstrap --------------------------------------------------------------


async def get_default_organization(db: AsyncSession) -> Organization | None:
    result = await db.execute(
        select(Organization).where(Organization.slug == settings.default_org_slug)
    )
    return result.scalar_one_or_none()


async def bootstrap_default_identity(db: AsyncSession) -> tuple[Organization, Team, User]:
    """Idempotently ensure the default org, workspace, and admin user exist."""
    org = await get_default_organization(db)
    if org is None:
        org = Organization(name=settings.default_org_name, slug=settings.default_org_slug)
        db.add(org)
        await db.flush()

    team_res = await db.execute(
        select(Team).where(Team.organization_id == org.id).order_by(Team.created_at)
    )
    team = team_res.scalars().first()
    if team is None:
        team = Team(
            organization_id=org.id,
            name=settings.default_workspace_name,
            slug=_slugify(settings.default_workspace_name),
        )
        db.add(team)
        await db.flush()

    user_res = await db.execute(select(User).where(User.email == settings.default_admin_email))
    admin = user_res.scalar_one_or_none()
    if admin is None:
        admin = User(
            email=settings.default_admin_email,
            name="Administrator",
            password_hash=(
                hash_password(settings.default_admin_password)
                if settings.default_admin_password
                else None
            ),
        )
        db.add(admin)
        await db.flush()

    mem_res = await db.execute(
        select(Membership).where(
            Membership.user_id == admin.id, Membership.team_id == team.id
        )
    )
    if mem_res.scalar_one_or_none() is None:
        db.add(Membership(user_id=admin.id, team_id=team.id, role=ROLE_ADMIN))
        await db.flush()

    return org, team, admin


async def system_context(db: AsyncSession) -> AuthContext:
    """An admin :class:`AuthContext` bound to the default org/workspace.

    Used by non-request entry points (startup auto-setup, the MCP server, seed
    scripts) that act on behalf of the deployment rather than an end user.
    """
    org, team, admin = await bootstrap_default_identity(db)
    return AuthContext(
        user=admin,
        organization_id=org.id,
        workspace_id=team.id,
        role=ROLE_ADMIN,
    )


# --- Teams ------------------------------------------------------------------


async def list_teams(db: AsyncSession, ctx: AuthContext) -> list[Team]:
    """Teams in the caller's organization."""
    result = await db.execute(
        select(Team)
        .where(Team.organization_id == ctx.organization_id)
        .order_by(Team.created_at)
    )
    return list(result.scalars().all())


async def list_my_memberships(db: AsyncSession, user: User) -> list[Membership]:
    result = await db.execute(
        select(Membership)
        .where(Membership.user_id == user.id)
        .options(selectinload(Membership.team))
        .order_by(Membership.created_at)
    )
    return list(result.scalars().all())


async def create_team(db: AsyncSession, ctx: AuthContext, name: str) -> Team:
    ctx.require_role(ROLE_ADMIN)
    team = Team(organization_id=ctx.organization_id, name=name, slug=_slugify(name))
    db.add(team)
    await db.flush()
    # The creator joins their new team as admin.
    db.add(Membership(user_id=ctx.user_id, team_id=team.id, role=ROLE_ADMIN))
    await db.flush()
    return team


async def _get_team_in_org(db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID) -> Team:
    team = await db.get(Team, team_id)
    if team is None or team.organization_id != ctx.organization_id:
        raise NotFoundError("Team", str(team_id))
    return team


async def list_memberships(
    db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID
) -> list[Membership]:
    await _get_team_in_org(db, ctx, team_id)
    result = await db.execute(
        select(Membership)
        .where(Membership.team_id == team_id)
        .options(selectinload(Membership.user))
        .order_by(Membership.created_at)
    )
    return list(result.scalars().all())


async def add_membership(
    db: AsyncSession,
    ctx: AuthContext,
    team_id: uuid.UUID,
    email: str,
    role: str,
) -> Membership:
    """Add a user (by email) to a team. Admin-only."""
    ctx.require_role(ROLE_ADMIN)
    if role not in ROLES:
        raise ValidationError(f"Invalid role '{role}'. Must be one of {list(ROLES)}.")
    await _get_team_in_org(db, ctx, team_id)

    user_res = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = user_res.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User", email)

    mem_res = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.team_id == team_id
        )
    )
    membership = mem_res.scalar_one_or_none()
    if membership is not None:
        membership.role = role
    else:
        membership = Membership(user_id=user.id, team_id=team_id, role=role)
        db.add(membership)
    await db.flush()
    return membership


async def remove_membership(
    db: AsyncSession, ctx: AuthContext, team_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    ctx.require_role(ROLE_ADMIN)
    await _get_team_in_org(db, ctx, team_id)
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.team_id == team_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Membership", f"{user_id} in {team_id}")
    await db.delete(membership)
    await db.flush()


# --- API keys ---------------------------------------------------------------


async def create_api_key(
    db: AsyncSession,
    user: User,
    name: str,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """Create an API key for ``user``. Returns ``(record, plaintext)``.

    The plaintext is returned exactly once and never persisted.
    """
    plaintext, key_hash, prefix = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        name=name,
        key_hash=key_hash,
        key_prefix=prefix,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    return api_key, plaintext


async def list_api_keys(db: AsyncSession, user: User) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, user: User, key_id: uuid.UUID) -> None:
    api_key = await db.get(ApiKey, key_id)
    if api_key is None or api_key.user_id != user.id:
        raise NotFoundError("ApiKey", str(key_id))
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
    await db.flush()
