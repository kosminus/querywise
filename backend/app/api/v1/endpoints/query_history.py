import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.query import QueryHistoryResponse
from app.core.auth import AuthContext, get_org_context
from app.core.exceptions import NotFoundError
from app.db.models.connection import DatabaseConnection
from app.db.models.query_history import QueryExecution
from app.db.session import get_db

router = APIRouter(prefix="/query-history", tags=["query_history"])


def _workspace_scoped(ctx: AuthContext):
    """History rows whose connection lives in the caller's workspace."""
    return (
        select(QueryExecution)
        .join(DatabaseConnection, QueryExecution.connection_id == DatabaseConnection.id)
        .where(
            QueryExecution.organization_id == ctx.organization_id,
            DatabaseConnection.workspace_id == ctx.workspace_id,
        )
    )


@router.get("", response_model=list[QueryHistoryResponse])
async def list_query_history(
    connection_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    stmt = _workspace_scoped(ctx).order_by(QueryExecution.created_at.desc())
    if connection_id:
        stmt = stmt.where(QueryExecution.connection_id == connection_id)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_scoped_execution(
    db: AsyncSession, ctx: AuthContext, execution_id: uuid.UUID
) -> QueryExecution:
    stmt = _workspace_scoped(ctx).where(QueryExecution.id == execution_id)
    execution = (await db.execute(stmt)).scalar_one_or_none()
    if not execution:
        raise NotFoundError("QueryExecution", str(execution_id))
    return execution


@router.get("/{execution_id}", response_model=QueryHistoryResponse)
async def get_query_execution(
    execution_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    return await _get_scoped_execution(db, ctx, execution_id)


@router.patch("/{execution_id}/favorite")
async def toggle_favorite(
    execution_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    execution = await _get_scoped_execution(db, ctx, execution_id)
    execution.is_favorite = not execution.is_favorite
    await db.flush()
    return {"is_favorite": execution.is_favorite}
