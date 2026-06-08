import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.dashboard import (
    DashboardCreate,
    DashboardResponse,
    DashboardTileCreate,
    DashboardTileResponse,
    DashboardTileUpdate,
    DashboardUpdate,
    TileLayoutUpdate,
    TileRunRequest,
    TileRunResponse,
)
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import dashboard_service

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("", response_model=list[DashboardResponse])
async def list_dashboards(
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.list_dashboards(db, ctx)


@router.post("", response_model=DashboardResponse, status_code=201)
async def create_dashboard(
    body: DashboardCreate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["filters"] = [f.model_dump() for f in body.filters]
    return await dashboard_service.create_dashboard(db, ctx, **data)


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_dashboard(db, dashboard_id, ctx)


@router.put("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    body: DashboardUpdate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    if "filters" in updates and body.filters is not None:
        updates["filters"] = [f.model_dump() for f in body.filters]
    return await dashboard_service.update_dashboard(db, dashboard_id, ctx, updates)


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    await dashboard_service.delete_dashboard(db, dashboard_id, ctx)


# --------------------------------------------------------------------------- #
# Tiles
# --------------------------------------------------------------------------- #
@router.post("/{dashboard_id}/tiles", response_model=DashboardTileResponse, status_code=201)
async def add_tile(
    dashboard_id: uuid.UUID,
    body: DashboardTileCreate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["position"] = body.position.model_dump()
    return await dashboard_service.add_tile(db, dashboard_id, ctx, data)


@router.put("/{dashboard_id}/tiles/{tile_id}", response_model=DashboardTileResponse)
async def update_tile(
    dashboard_id: uuid.UUID,
    tile_id: uuid.UUID,
    body: DashboardTileUpdate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    if "position" in updates and body.position is not None:
        updates["position"] = body.position.model_dump()
    return await dashboard_service.update_tile(db, dashboard_id, tile_id, ctx, updates)


@router.delete("/{dashboard_id}/tiles/{tile_id}", status_code=204)
async def delete_tile(
    dashboard_id: uuid.UUID,
    tile_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    await dashboard_service.delete_tile(db, dashboard_id, tile_id, ctx)


@router.put("/{dashboard_id}/layout", response_model=DashboardResponse)
async def update_layout(
    dashboard_id: uuid.UUID,
    body: TileLayoutUpdate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    layout = [item.model_dump() for item in body.layout]
    return await dashboard_service.update_layout(db, dashboard_id, ctx, layout)


@router.post("/{dashboard_id}/tiles/{tile_id}/run", response_model=TileRunResponse)
async def run_tile(
    dashboard_id: uuid.UUID,
    tile_id: uuid.UUID,
    body: TileRunRequest,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.run_tile(
        db, dashboard_id, tile_id, ctx, body.filters, refresh=body.refresh
    )
