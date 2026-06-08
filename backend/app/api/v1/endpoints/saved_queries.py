import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_connection_read, require_connection_write
from app.api.v1.schemas.chart import ChartCreate, ChartResponse, ChartUpdate
from app.api.v1.schemas.saved_query import (
    SavedQueryCreate,
    SavedQueryResponse,
    SavedQueryRunRequest,
    SavedQueryRunResponse,
    SavedQueryUpdate,
)
from app.api.v1.schemas.catalog import LineageRefResponse
from app.api.v1.schemas.semantic_version import SemanticVersionResponse, StatusTransition
from app.core.auth import AuthContext
from app.core.exceptions import AppError, NotFoundError
from app.db.models.artifact_dependency import ARTIFACT_SAVED_QUERY
from app.db.models.chart import Chart
from app.db.models.saved_query import SavedQuery
from app.db.models.semantic_version import ENTITY_SAVED_QUERY
from app.db.session import get_db
from app.services import lineage_service, saved_query_service, versioning_service

router = APIRouter(tags=["saved-queries"])


async def _get_saved_query(
    db: AsyncSession, connection_id: uuid.UUID, saved_query_id: uuid.UUID
) -> SavedQuery:
    saved = await db.get(SavedQuery, saved_query_id)
    if not saved or saved.connection_id != connection_id:
        raise NotFoundError("SavedQuery", str(saved_query_id))
    return saved


# --------------------------------------------------------------------------- #
# Saved-query CRUD
# --------------------------------------------------------------------------- #
@router.get(
    "/connections/{connection_id}/saved-queries",
    response_model=list[SavedQueryResponse],
)
async def list_saved_queries(
    connection_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedQuery)
        .where(SavedQuery.connection_id == connection_id)
        .order_by(SavedQuery.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/connections/{connection_id}/saved-queries",
    response_model=SavedQueryResponse,
    status_code=201,
)
async def create_saved_query(
    connection_id: uuid.UUID,
    body: SavedQueryCreate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["params"] = [p.model_dump() for p in body.params]
    saved = SavedQuery(
        connection_id=connection_id,
        organization_id=ctx.organization_id,
        owner_id=ctx.user_id,
        **data,
    )
    db.add(saved)
    await db.flush()
    await lineage_service.recompute_saved_query(db, ctx, saved)
    return saved


@router.get(
    "/connections/{connection_id}/saved-queries/{saved_query_id}",
    response_model=SavedQueryResponse,
)
async def get_saved_query(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    return await _get_saved_query(db, connection_id, saved_query_id)


@router.put(
    "/connections/{connection_id}/saved-queries/{saved_query_id}",
    response_model=SavedQueryResponse,
)
async def update_saved_query(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    body: SavedQueryUpdate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    saved = await _get_saved_query(db, connection_id, saved_query_id)
    updates = body.model_dump(exclude_unset=True)
    # Status changes go through the governed lifecycle, not a raw field write.
    new_status = updates.pop("status", None)
    if "params" in updates and body.params is not None:
        updates["params"] = [p.model_dump() for p in body.params]
    for key, value in updates.items():
        setattr(saved, key, value)
    # A content edit bumps the version and appends a changelog snapshot.
    if updates:
        await versioning_service.record_edit(db, ctx, ENTITY_SAVED_QUERY, saved)
    if new_status is not None and new_status != saved.status:
        await versioning_service.transition_status(db, ctx, ENTITY_SAVED_QUERY, saved, new_status)
    await db.flush()
    if "pinned_sql" in updates:
        await lineage_service.recompute_saved_query(db, ctx, saved)
    return saved


@router.delete(
    "/connections/{connection_id}/saved-queries/{saved_query_id}",
    status_code=204,
)
async def delete_saved_query(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    saved = await _get_saved_query(db, connection_id, saved_query_id)
    await db.delete(saved)
    await db.flush()


@router.post(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/clone",
    response_model=SavedQueryResponse,
    status_code=201,
)
async def clone_saved_query(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    src = await _get_saved_query(db, connection_id, saved_query_id)
    clone = SavedQuery(
        connection_id=connection_id,
        organization_id=ctx.organization_id,
        owner_id=ctx.user_id,
        name=f"{src.name} (copy)",
        description=src.description,
        nl_question=src.nl_question,
        pinned_sql=src.pinned_sql,
        params=src.params,
        status="draft",
        is_public=False,
    )
    db.add(clone)
    await db.flush()
    await lineage_service.recompute_saved_query(db, ctx, clone)
    return clone


# --------------------------------------------------------------------------- #
# Certification lifecycle + version history
# --------------------------------------------------------------------------- #
@router.post(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/status",
    response_model=SavedQueryResponse,
)
async def transition_saved_query_status(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    body: StatusTransition,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    saved = await _get_saved_query(db, connection_id, saved_query_id)
    await versioning_service.transition_status(
        db, ctx, ENTITY_SAVED_QUERY, saved, body.status, reason=body.reason
    )
    await db.flush()
    return saved


@router.get(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/versions",
    response_model=list[SemanticVersionResponse],
)
async def list_saved_query_versions(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    await _get_saved_query(db, connection_id, saved_query_id)
    return await versioning_service.list_versions(db, ENTITY_SAVED_QUERY, saved_query_id)


@router.get(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/versions/{version}",
    response_model=SemanticVersionResponse,
)
async def get_saved_query_version(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    version: int,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    await _get_saved_query(db, connection_id, saved_query_id)
    snap = await versioning_service.get_version(db, ENTITY_SAVED_QUERY, saved_query_id, version)
    if snap is None:
        raise NotFoundError("SavedQueryVersion", f"{saved_query_id}@{version}")
    return snap


@router.get(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/lineage",
    response_model=list[LineageRefResponse],
)
async def get_saved_query_lineage(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    """What tables/columns this saved query touches."""
    await _get_saved_query(db, connection_id, saved_query_id)
    return await lineage_service.refs_for_artifact(db, ARTIFACT_SAVED_QUERY, saved_query_id)


# --------------------------------------------------------------------------- #
# Run + export
# --------------------------------------------------------------------------- #
@router.post(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/run",
    response_model=SavedQueryRunResponse,
)
async def run_saved_query(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    body: SavedQueryRunRequest,
    ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    saved = await _get_saved_query(db, connection_id, saved_query_id)
    return await saved_query_service.run_saved_query(
        db, saved, ctx, body.params, refresh=body.refresh
    )


@router.get("/connections/{connection_id}/saved-queries/{saved_query_id}/export")
async def export_saved_query(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    format: str = Query("csv", pattern="^(csv|json|xlsx)$"),
    ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    saved = await _get_saved_query(db, connection_id, saved_query_id)
    result = await saved_query_service.run_saved_query(db, saved, ctx, {})
    columns: list[str] = result["columns"]
    rows: list[list] = result["rows"]
    base = saved.name.replace(" ", "_") or "result"

    if format == "json":
        payload = [dict(zip(columns, row, strict=False)) for row in rows]
        return StreamingResponse(
            iter([json.dumps(payload, default=str)]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{base}.json"'},
        )

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        writer.writerows(rows)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{base}.csv"'},
        )

    # xlsx — optional dependency
    try:
        from openpyxl import Workbook  # type: ignore[import-untyped]
    except ImportError as exc:
        raise AppError(
            "XLSX export requires the 'openpyxl' package (install the backend '[export]' extra).",
            status_code=422,
        ) from exc

    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append(list(row))
    buf_bytes = io.BytesIO()
    wb.save(buf_bytes)
    buf_bytes.seek(0)
    return StreamingResponse(
        buf_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'},
    )


# --------------------------------------------------------------------------- #
# Charts (sub-resource of a saved query)
# --------------------------------------------------------------------------- #
async def _get_chart(db: AsyncSession, saved_query_id: uuid.UUID, chart_id: uuid.UUID) -> Chart:
    chart = await db.get(Chart, chart_id)
    if not chart or chart.saved_query_id != saved_query_id:
        raise NotFoundError("Chart", str(chart_id))
    return chart


@router.get(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/charts",
    response_model=list[ChartResponse],
)
async def list_charts(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    await _get_saved_query(db, connection_id, saved_query_id)
    result = await db.execute(
        select(Chart).where(Chart.saved_query_id == saved_query_id).order_by(Chart.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/charts",
    response_model=ChartResponse,
    status_code=201,
)
async def create_chart(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    body: ChartCreate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    await _get_saved_query(db, connection_id, saved_query_id)
    chart = Chart(
        organization_id=ctx.organization_id,
        saved_query_id=saved_query_id,
        **body.model_dump(),
    )
    db.add(chart)
    await db.flush()
    return chart


@router.put(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/charts/{chart_id}",
    response_model=ChartResponse,
)
async def update_chart(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    chart_id: uuid.UUID,
    body: ChartUpdate,
    _ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    await _get_saved_query(db, connection_id, saved_query_id)
    chart = await _get_chart(db, saved_query_id, chart_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(chart, key, value)
    await db.flush()
    return chart


@router.delete(
    "/connections/{connection_id}/saved-queries/{saved_query_id}/charts/{chart_id}",
    status_code=204,
)
async def delete_chart(
    connection_id: uuid.UUID,
    saved_query_id: uuid.UUID,
    chart_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    await _get_saved_query(db, connection_id, saved_query_id)
    chart = await _get_chart(db, saved_query_id, chart_id)
    await db.delete(chart)
    await db.flush()
