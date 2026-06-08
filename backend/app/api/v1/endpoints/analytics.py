"""Cost & usage analytics. Admin-only, org-scoped, windowed by ``days``."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.analytics import (
    CostByEntry,
    SlowestQuery,
    TableUsage,
    UsageSummary,
)
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import cost_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@router.get("/usage", response_model=UsageSummary)
async def usage(
    days: int = Query(30, ge=1, le=365),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_role("admin")
    return await cost_service.usage_summary(db, ctx.organization_id, _since(days))


@router.get("/cost", response_model=list[CostByEntry])
async def cost_by(
    by: str = Query("workspace", pattern="^(workspace|user|connection)$"),
    days: int = Query(30, ge=1, le=365),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_role("admin")
    return await cost_service.cost_by(db, ctx.organization_id, by, _since(days))


@router.get("/slowest", response_model=list[SlowestQuery])
async def slowest(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_role("admin")
    return await cost_service.slowest_queries(db, ctx.organization_id, _since(days), limit)


@router.get("/tables", response_model=list[TableUsage])
async def tables(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    ctx.require_role("admin")
    return await cost_service.most_queried_tables(db, ctx.organization_id, _since(days), limit)
