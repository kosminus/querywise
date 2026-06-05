import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_connection_read, require_connection_write
from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError
from app.db.models.sample_query import SampleQuery
from app.db.session import get_db
from app.services.embedding_service import embed_sample_query

router = APIRouter(tags=["sample_queries"])


class SampleQueryCreate(BaseModel):
    natural_language: str = Field(min_length=1)
    sql_query: str = Field(min_length=1)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_validated: bool = False


class SampleQueryUpdate(BaseModel):
    natural_language: str | None = Field(default=None, min_length=1)
    sql_query: str | None = Field(default=None, min_length=1)
    description: str | None = None
    tags: list[str] | None = None
    is_validated: bool | None = None


class SampleQueryResponse(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    natural_language: str
    sql_query: str
    description: str | None
    tags: list[str] | None
    is_validated: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


@router.get(
    "/connections/{connection_id}/sample-queries",
    response_model=list[SampleQueryResponse],
)
async def list_sample_queries(
    connection_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SampleQuery)
        .where(SampleQuery.connection_id == connection_id)
        .order_by(SampleQuery.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/connections/{connection_id}/sample-queries",
    response_model=SampleQueryResponse,
    status_code=201,
)
async def create_sample_query(
    connection_id: uuid.UUID,
    body: SampleQueryCreate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    sq = SampleQuery(
        connection_id=connection_id,
        organization_id=ctx.organization_id,
        created_by_id=ctx.user_id,
        **body.model_dump(),
    )
    db.add(sq)
    await db.flush()
    try:
        sq.question_embedding = await embed_sample_query(sq)
    except Exception:
        pass
    return sq


@router.put(
    "/connections/{connection_id}/sample-queries/{sq_id}",
    response_model=SampleQueryResponse,
)
async def update_sample_query(
    connection_id: uuid.UUID,
    sq_id: uuid.UUID,
    body: SampleQueryUpdate,
    _ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    sq = await db.get(SampleQuery, sq_id)
    if not sq or sq.connection_id != connection_id:
        raise NotFoundError("SampleQuery", str(sq_id))
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(sq, key, value)
    await db.flush()
    try:
        sq.question_embedding = await embed_sample_query(sq)
    except Exception:
        pass
    return sq


@router.delete(
    "/connections/{connection_id}/sample-queries/{sq_id}",
    status_code=204,
)
async def delete_sample_query(
    connection_id: uuid.UUID,
    sq_id: uuid.UUID,
    _ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    sq = await db.get(SampleQuery, sq_id)
    if not sq or sq.connection_id != connection_id:
        raise NotFoundError("SampleQuery", str(sq_id))
    await db.delete(sq)
    await db.flush()
