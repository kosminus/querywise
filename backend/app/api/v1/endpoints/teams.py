import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.team import (
    MembershipCreate,
    MembershipResponse,
    TeamCreate,
    TeamResponse,
)
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import identity_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    teams = await identity_service.list_teams(db, ctx)
    return [TeamResponse.model_validate(t) for t in teams]


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    team = await identity_service.create_team(db, ctx, body.name)
    return TeamResponse.model_validate(team)


@router.get("/{team_id}/members", response_model=list[MembershipResponse])
async def list_members(
    team_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    memberships = await identity_service.list_memberships(db, ctx, team_id)
    return [
        MembershipResponse(
            id=m.id,
            team_id=m.team_id,
            user_id=m.user_id,
            user_email=m.user.email,
            user_name=m.user.name,
            role=m.role,
            created_at=m.created_at,
        )
        for m in memberships
    ]


@router.post("/{team_id}/members", response_model=MembershipResponse, status_code=201)
async def add_member(
    team_id: uuid.UUID,
    body: MembershipCreate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    membership = await identity_service.add_membership(db, ctx, team_id, body.email, body.role)
    await db.refresh(membership, ["user"])
    return MembershipResponse(
        id=membership.id,
        team_id=membership.team_id,
        user_id=membership.user_id,
        user_email=membership.user.email,
        user_name=membership.user.name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    await identity_service.remove_membership(db, ctx, team_id, user_id)
