"""Scheduled-report CRUD + manual trigger. Workspace-scoped (like dashboards)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.schedule import (
    ScheduleCreate,
    ScheduleResponse,
    ScheduleRunResponse,
    ScheduleUpdate,
)
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import schedule_service

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    return await schedule_service.list_schedules(db, ctx)


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    if data.get("threshold") is not None:
        data["threshold"] = body.threshold.model_dump()
    return await schedule_service.create_schedule(db, ctx, **data)


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    return await schedule_service.get_schedule(db, schedule_id, ctx)


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: uuid.UUID,
    body: ScheduleUpdate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    if "threshold" in updates and body.threshold is not None:
        updates["threshold"] = body.threshold.model_dump()
    return await schedule_service.update_schedule(db, schedule_id, ctx, updates)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    await schedule_service.delete_schedule(db, schedule_id, ctx)


@router.post("/{schedule_id}/run", response_model=ScheduleRunResponse)
async def run_schedule_now(
    schedule_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a schedule immediately without changing its cron cadence."""
    return await schedule_service.run_now(db, schedule_id, ctx)
