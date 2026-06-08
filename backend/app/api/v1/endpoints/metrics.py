import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_connection_read, require_connection_write
from app.api.v1.schemas.metric import MetricCreate, MetricResponse, MetricUpdate
from app.api.v1.schemas.catalog import LineageRefResponse
from app.api.v1.schemas.semantic_version import SemanticVersionResponse, StatusTransition
from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError
from app.db.models.artifact_dependency import ARTIFACT_METRIC
from app.db.models.metric import MetricDefinition
from app.db.models.semantic_version import ENTITY_METRIC
from app.db.session import get_db
from app.services import lineage_service, versioning_service
from app.services.embedding_service import embed_metric

router = APIRouter(tags=["metrics"])


@router.get(
    "/connections/{connection_id}/metrics",
    response_model=list[MetricResponse],
)
async def list_metrics(
    connection_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MetricDefinition)
        .where(MetricDefinition.connection_id == connection_id)
        .order_by(MetricDefinition.display_name)
    )
    return list(result.scalars().all())


@router.post(
    "/connections/{connection_id}/metrics",
    response_model=MetricResponse,
    status_code=201,
)
async def create_metric(
    connection_id: uuid.UUID,
    body: MetricCreate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    metric = MetricDefinition(
        connection_id=connection_id,
        organization_id=ctx.organization_id,
        created_by_id=ctx.user_id,
        **body.model_dump(),
    )
    db.add(metric)
    await db.flush()
    try:
        metric.metric_embedding = await embed_metric(metric)
    except Exception:
        pass
    await lineage_service.recompute_metric(db, ctx, metric)
    return metric


@router.get(
    "/connections/{connection_id}/metrics/{metric_id}",
    response_model=MetricResponse,
)
async def get_metric(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))
    return metric


@router.put(
    "/connections/{connection_id}/metrics/{metric_id}",
    response_model=MetricResponse,
)
async def update_metric(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    body: MetricUpdate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))

    for key, value in body.model_dump(exclude_none=True).items():
        setattr(metric, key, value)

    await versioning_service.record_edit(db, ctx, ENTITY_METRIC, metric)
    await db.flush()
    try:
        metric.metric_embedding = await embed_metric(metric)
    except Exception:
        pass
    await lineage_service.recompute_metric(db, ctx, metric)
    return metric


@router.delete(
    "/connections/{connection_id}/metrics/{metric_id}",
    status_code=204,
)
async def delete_metric(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))
    await db.delete(metric)
    await db.flush()


# --------------------------------------------------------------------------- #
# Certification lifecycle + version history
# --------------------------------------------------------------------------- #
@router.post(
    "/connections/{connection_id}/metrics/{metric_id}/status",
    response_model=MetricResponse,
)
async def transition_metric_status(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    body: StatusTransition,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))
    await versioning_service.transition_status(
        db, ctx, ENTITY_METRIC, metric, body.status, reason=body.reason
    )
    await db.flush()
    return metric


@router.get(
    "/connections/{connection_id}/metrics/{metric_id}/versions",
    response_model=list[SemanticVersionResponse],
)
async def list_metric_versions(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))
    return await versioning_service.list_versions(db, ENTITY_METRIC, metric_id)


@router.get(
    "/connections/{connection_id}/metrics/{metric_id}/versions/{version}",
    response_model=SemanticVersionResponse,
)
async def get_metric_version(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    version: int,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))
    snap = await versioning_service.get_version(db, ENTITY_METRIC, metric_id, version)
    if snap is None:
        raise NotFoundError("MetricVersion", f"{metric_id}@{version}")
    return snap


@router.get(
    "/connections/{connection_id}/metrics/{metric_id}/lineage",
    response_model=list[LineageRefResponse],
)
async def get_metric_lineage(
    connection_id: uuid.UUID,
    metric_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    """What tables/columns this metric's SQL touches."""
    metric = await db.get(MetricDefinition, metric_id)
    if not metric or metric.connection_id != connection_id:
        raise NotFoundError("Metric", str(metric_id))
    return await lineage_service.refs_for_artifact(db, ARTIFACT_METRIC, metric_id)
