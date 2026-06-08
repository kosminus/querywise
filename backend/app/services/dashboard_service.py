"""Dashboard service — workspace-scoped CRUD, tile management, and tile runs.

Dashboards are the first workspace-scoped artifact (saved queries/charts are
connection-scoped). Tiles run their saved query through
:func:`saved_query_service.run_saved_query`, which authorizes via the saved
query's connection and reuses the Milestone-1 result cache. Dashboard-level
filter values are passed straight through as the run's supplied params; a tile
only consumes the filters its SQL references (``render_sql`` ignores the rest).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import AuthContext
from app.core.exceptions import AuthorizationError, NotFoundError
from app.db.models.chart import Chart
from app.db.models.dashboard import Dashboard
from app.db.models.dashboard_tile import DashboardTile
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR
from app.db.models.saved_query import SavedQuery
from app.services import saved_query_service


def _assert_access(dashboard: Dashboard, ctx: AuthContext, *, write: bool = False) -> None:
    """Enforce workspace scoping + role for a dashboard.

    Cross-workspace access raises 404 (don't leak existence); private dashboards
    are visible only to their owner or a workspace admin.
    """
    if (
        dashboard.organization_id != ctx.organization_id
        or dashboard.workspace_id != ctx.workspace_id
    ):
        raise NotFoundError("Dashboard", str(dashboard.id))
    if (
        not dashboard.is_public
        and dashboard.owner_id != ctx.user_id
        and not ctx.has_role(ROLE_ADMIN)
    ):
        raise AuthorizationError("This dashboard is private to its owner.")
    if write:
        ctx.require_role(ROLE_EDITOR)


async def _load(
    db: AsyncSession, dashboard_id: uuid.UUID, ctx: AuthContext, *, write: bool = False
) -> Dashboard:
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id).options(selectinload(Dashboard.tiles))
    )
    dashboard = result.scalar_one_or_none()
    if dashboard is None:
        raise NotFoundError("Dashboard", str(dashboard_id))
    _assert_access(dashboard, ctx, write=write)
    return dashboard


async def _finalize(db: AsyncSession, dashboard: Dashboard) -> Dashboard:
    """Flush and repopulate server-side columns after a write.

    UPDATEs don't use RETURNING for ``onupdate`` timestamps the way INSERTs do,
    so the modified rows' attributes are left expired; without an explicit
    refresh the response serializer would trigger a lazy load outside the async
    context (MissingGreenlet). Refresh the scalar columns and reload the tiles.
    """
    await db.flush()
    await db.refresh(dashboard)
    await db.refresh(dashboard, ["tiles"])
    return dashboard


async def list_dashboards(db: AsyncSession, ctx: AuthContext) -> list[Dashboard]:
    result = await db.execute(
        select(Dashboard)
        .where(
            Dashboard.organization_id == ctx.organization_id,
            Dashboard.workspace_id == ctx.workspace_id,
        )
        .options(selectinload(Dashboard.tiles))
        .order_by(Dashboard.updated_at.desc())
    )
    dashboards = list(result.scalars().all())
    # Hide other people's private dashboards from non-admins.
    if not ctx.has_role(ROLE_ADMIN):
        dashboards = [d for d in dashboards if d.is_public or d.owner_id == ctx.user_id]
    return dashboards


async def get_dashboard(db: AsyncSession, dashboard_id: uuid.UUID, ctx: AuthContext) -> Dashboard:
    return await _load(db, dashboard_id, ctx)


async def create_dashboard(db: AsyncSession, ctx: AuthContext, **data: Any) -> Dashboard:
    ctx.require_role(ROLE_EDITOR)
    dashboard = Dashboard(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        owner_id=ctx.user_id,
        **data,
    )
    db.add(dashboard)
    await db.flush()
    await db.refresh(dashboard, ["tiles"])
    return dashboard


async def update_dashboard(
    db: AsyncSession, dashboard_id: uuid.UUID, ctx: AuthContext, updates: dict[str, Any]
) -> Dashboard:
    dashboard = await _load(db, dashboard_id, ctx, write=True)
    for key, value in updates.items():
        setattr(dashboard, key, value)
    return await _finalize(db, dashboard)


async def delete_dashboard(db: AsyncSession, dashboard_id: uuid.UUID, ctx: AuthContext) -> None:
    dashboard = await _load(db, dashboard_id, ctx, write=True)
    await db.delete(dashboard)
    await db.flush()


# --------------------------------------------------------------------------- #
# Tiles
# --------------------------------------------------------------------------- #
async def _get_saved_query(
    db: AsyncSession, saved_query_id: uuid.UUID, ctx: AuthContext
) -> SavedQuery:
    saved = await db.get(SavedQuery, saved_query_id)
    if saved is None or saved.organization_id != ctx.organization_id:
        raise NotFoundError("SavedQuery", str(saved_query_id))
    return saved


def _get_tile(dashboard: Dashboard, tile_id: uuid.UUID) -> DashboardTile:
    for tile in dashboard.tiles:
        if tile.id == tile_id:
            return tile
    raise NotFoundError("DashboardTile", str(tile_id))


async def add_tile(
    db: AsyncSession, dashboard_id: uuid.UUID, ctx: AuthContext, data: dict[str, Any]
) -> DashboardTile:
    dashboard = await _load(db, dashboard_id, ctx, write=True)
    # Ensure the saved query is visible in this workspace before pinning it.
    await _get_saved_query(db, data["saved_query_id"], ctx)
    tile = DashboardTile(
        organization_id=ctx.organization_id,
        dashboard_id=dashboard.id,
        **data,
    )
    db.add(tile)
    await db.flush()
    return tile


async def update_tile(
    db: AsyncSession,
    dashboard_id: uuid.UUID,
    tile_id: uuid.UUID,
    ctx: AuthContext,
    updates: dict[str, Any],
) -> DashboardTile:
    dashboard = await _load(db, dashboard_id, ctx, write=True)
    tile = _get_tile(dashboard, tile_id)
    for key, value in updates.items():
        setattr(tile, key, value)
    await db.flush()
    await db.refresh(tile)
    return tile


async def delete_tile(
    db: AsyncSession, dashboard_id: uuid.UUID, tile_id: uuid.UUID, ctx: AuthContext
) -> None:
    dashboard = await _load(db, dashboard_id, ctx, write=True)
    tile = _get_tile(dashboard, tile_id)
    await db.delete(tile)
    await db.flush()


async def update_layout(
    db: AsyncSession,
    dashboard_id: uuid.UUID,
    ctx: AuthContext,
    layout: list[dict[str, Any]],
) -> Dashboard:
    dashboard = await _load(db, dashboard_id, ctx, write=True)
    by_id = {tile.id: tile for tile in dashboard.tiles}
    for item in layout:
        tile = by_id.get(item["tile_id"])
        if tile is not None:
            tile.position = {"x": item["x"], "y": item["y"], "w": item["w"], "h": item["h"]}
    return await _finalize(db, dashboard)


async def run_tile(
    db: AsyncSession,
    dashboard_id: uuid.UUID,
    tile_id: uuid.UUID,
    ctx: AuthContext,
    filter_values: dict[str, Any],
    *,
    refresh: bool = False,
) -> dict:
    dashboard = await _load(db, dashboard_id, ctx)
    tile = _get_tile(dashboard, tile_id)
    saved = await _get_saved_query(db, tile.saved_query_id, ctx)

    # Dashboard filter values are the supplied params; run_saved_query authorizes
    # via the saved query's connection and uses the M1 result cache.
    result = await saved_query_service.run_saved_query(
        db, saved, ctx, filter_values, refresh=refresh
    )

    if tile.chart_id is not None:
        chart = await db.get(Chart, tile.chart_id)
        if chart is not None and chart.saved_query_id == saved.id:
            result["chart_type"] = chart.chart_type
            result["chart_config"] = chart.config
    return result
