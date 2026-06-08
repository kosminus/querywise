"""Data-policy CRUD. Connection-scoped; editor+ to modify (admins typically)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_connection_read, require_connection_write
from app.api.v1.schemas.data_policy import (
    DataPolicyCreate,
    DataPolicyResponse,
    DataPolicyUpdate,
)
from app.core.auth import AuthContext
from app.db.session import get_db
from app.services import policy_service

router = APIRouter(tags=["policies"])

_BASE = "/connections/{connection_id}/policies"


@router.get(_BASE, response_model=list[DataPolicyResponse])
async def list_policies(
    connection_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    return await policy_service.list_policies(db, connection_id)


@router.post(_BASE, response_model=DataPolicyResponse, status_code=201)
async def create_policy(
    connection_id: uuid.UUID,
    body: DataPolicyCreate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    return await policy_service.create_policy(db, connection_id, ctx, **body.model_dump())


@router.get(_BASE + "/{policy_id}", response_model=DataPolicyResponse)
async def get_policy(
    connection_id: uuid.UUID,
    policy_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    return await policy_service.get_policy(db, connection_id, policy_id)


@router.put(_BASE + "/{policy_id}", response_model=DataPolicyResponse)
async def update_policy(
    connection_id: uuid.UUID,
    policy_id: uuid.UUID,
    body: DataPolicyUpdate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    return await policy_service.update_policy(
        db, connection_id, policy_id, ctx, body.model_dump(exclude_unset=True)
    )


@router.delete(_BASE + "/{policy_id}", status_code=204)
async def delete_policy(
    connection_id: uuid.UUID,
    policy_id: uuid.UUID,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    await policy_service.delete_policy(db, connection_id, policy_id, ctx)
