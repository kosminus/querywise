from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.query import ExecuteSQLRequest, QueryRequest, SQLOnlyResponse
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import query_service

router = APIRouter(prefix="/query", tags=["query"])


@router.post("")
async def execute_query(
    body: QueryRequest,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Submit a natural language question and get SQL + results + interpretation."""
    result = await query_service.execute_nl_query(
        db, body.connection_id, body.question, ctx
    )
    return result


@router.post("/execute-sql")
async def execute_sql(
    body: ExecuteSQLRequest,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Execute user-provided SQL directly (no LLM generation)."""
    result = await query_service.execute_raw_sql(
        db, body.connection_id, body.sql, ctx, body.original_question
    )
    return result


@router.post("/sql-only", response_model=SQLOnlyResponse)
async def generate_sql_only(
    body: QueryRequest,
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Generate SQL without executing it."""
    result = await query_service.generate_sql_only(
        db, body.connection_id, body.question, ctx
    )
    return SQLOnlyResponse(**result)
