import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.connection import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionTestResult,
    ConnectionUpdate,
)
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import connection_service

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    connections = await connection_service.list_connections(db, ctx)
    return [
        ConnectionResponse(
            id=c.id,
            name=c.name,
            connector_type=c.connector_type,
            default_schema=c.default_schema,
            max_query_timeout_seconds=c.max_query_timeout_seconds,
            max_rows=c.max_rows,
            is_active=c.is_active,
            has_connection_string=bool(c.connection_string_encrypted),
            last_introspected_at=c.last_introspected_at,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in connections
    ]


@router.post("", response_model=ConnectionResponse, status_code=201)
async def create_connection(
    body: ConnectionCreate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    conn = await connection_service.create_connection(
        db,
        ctx,
        name=body.name,
        connector_type=body.connector_type,
        connection_string=body.connection_string,
        default_schema=body.default_schema,
        max_query_timeout_seconds=body.max_query_timeout_seconds,
        max_rows=body.max_rows,
    )
    return ConnectionResponse(
        id=conn.id,
        name=conn.name,
        connector_type=conn.connector_type,
        default_schema=conn.default_schema,
        max_query_timeout_seconds=conn.max_query_timeout_seconds,
        max_rows=conn.max_rows,
        is_active=conn.is_active,
        has_connection_string=True,
        last_introspected_at=conn.last_introspected_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    conn = await connection_service.get_connection(db, connection_id, ctx)
    return ConnectionResponse(
        id=conn.id,
        name=conn.name,
        connector_type=conn.connector_type,
        default_schema=conn.default_schema,
        max_query_timeout_seconds=conn.max_query_timeout_seconds,
        max_rows=conn.max_rows,
        is_active=conn.is_active,
        has_connection_string=bool(conn.connection_string_encrypted),
        last_introspected_at=conn.last_introspected_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.put("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    body: ConnectionUpdate,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    conn = await connection_service.update_connection(
        db, connection_id, ctx, **body.model_dump(exclude_none=True)
    )
    return ConnectionResponse(
        id=conn.id,
        name=conn.name,
        connector_type=conn.connector_type,
        default_schema=conn.default_schema,
        max_query_timeout_seconds=conn.max_query_timeout_seconds,
        max_rows=conn.max_rows,
        is_active=conn.is_active,
        has_connection_string=bool(conn.connection_string_encrypted),
        last_introspected_at=conn.last_introspected_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    await connection_service.delete_connection(db, connection_id, ctx)


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
async def test_connection(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    success, message = await connection_service.test_connection(db, connection_id, ctx)
    return ConnectionTestResult(success=success, message=message)
