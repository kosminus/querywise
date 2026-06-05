"""Shared FastAPI dependencies for authorization.

Metadata endpoints (glossary, metrics, dictionary, sample queries, knowledge,
schema) are keyed by ``connection_id`` — the workspace cascade root. These
dependencies resolve the caller's :class:`AuthContext` and assert access to the
connection in the path, so handlers can stay thin.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_org_context
from app.core.exceptions import NotFoundError
from app.db.models.schema_cache import CachedColumn, CachedTable
from app.db.session import get_db
from app.services import connection_service


async def require_connection_read(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Caller must be able to read the connection in the path."""
    await connection_service.get_connection(db, connection_id, ctx)
    return ctx


async def require_connection_write(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Caller must be an editor (or above) on the connection in the path."""
    await connection_service.get_connection(db, connection_id, ctx, write=True)
    return ctx


async def _connection_id_for_column(db: AsyncSession, column_id: uuid.UUID) -> uuid.UUID:
    result = await db.execute(
        select(CachedTable.connection_id)
        .join(CachedColumn, CachedColumn.table_id == CachedTable.id)
        .where(CachedColumn.id == column_id)
    )
    connection_id = result.scalar_one_or_none()
    if connection_id is None:
        raise NotFoundError("Column", str(column_id))
    return connection_id


async def require_column_read(
    column_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Caller must be able to read the connection owning the column in the path."""
    connection_id = await _connection_id_for_column(db, column_id)
    await connection_service.get_connection(db, connection_id, ctx)
    return ctx


async def require_column_write(
    column_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Caller must be an editor on the connection owning the column in the path."""
    connection_id = await _connection_id_for_column(db, column_id)
    await connection_service.get_connection(db, connection_id, ctx, write=True)
    return ctx
