import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_connection_read
from app.api.v1.schemas.catalog import (
    CatalogFacetsResponse,
    CatalogHitResponse,
    LineageRefResponse,
)
from app.core.auth import AuthContext
from app.db.session import get_db
from app.services import catalog_service, lineage_service

router = APIRouter(tags=["catalog"])


@router.get(
    "/connections/{connection_id}/catalog/search",
    response_model=list[CatalogHitResponse],
)
async def catalog_search(
    connection_id: uuid.UUID,
    q: str = Query("", description="Search text"),
    types: str | None = Query(None, description="Comma-separated hit types to include"),
    status: str | None = Query(None, description="Filter by certification status"),
    owner: str | None = Query(None, description="Filter by owner/creator id"),
    schema: str | None = Query(None, description="Filter tables/columns by schema"),
    limit: int = Query(50, ge=1, le=200),
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
    return await catalog_service.search(
        db,
        connection_id,
        q,
        types=type_list,
        status=status,
        owner=owner,
        schema=schema,
        limit=limit,
    )


@router.get(
    "/connections/{connection_id}/catalog/facets",
    response_model=CatalogFacetsResponse,
)
async def catalog_facets(
    connection_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    return await catalog_service.facets(db, connection_id)


@router.get(
    "/connections/{connection_id}/catalog/lineage",
    response_model=list[LineageRefResponse],
)
async def catalog_lineage_impact(
    connection_id: uuid.UUID,
    table: str = Query(..., description="Table name to find dependents of"),
    column: str | None = Query(None, description="Optional column name"),
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    """Impact view: which saved queries / metrics depend on a table (or column)."""
    return await lineage_service.dependents_of(db, connection_id, table, column)
