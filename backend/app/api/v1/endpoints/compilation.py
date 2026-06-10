"""Semantic layer compiler endpoints: runs + findings review."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_connection_read, require_connection_write
from app.api.v1.schemas.compilation import (
    BulkReviewRequest,
    BulkReviewResponse,
    CompilationFindingResponse,
    CompilationProgressResponse,
    CompilationRunCreate,
    CompilationRunResponse,
)
from app.core.auth import AuthContext
from app.db.session import get_db
from app.services import compilation_progress, compilation_service

router = APIRouter(tags=["compilation"])


def _with_progress(run) -> CompilationRunResponse:
    response = CompilationRunResponse.model_validate(run)
    p = compilation_progress.get_progress(str(run.connection_id))
    if p is not None and run.status in ("queued", "running"):
        response.progress = CompilationProgressResponse(
            total=p.total,
            completed=p.completed,
            stage=p.stage,
            status=p.status,
            error=p.error,
        )
    return response


@router.post(
    "/connections/{connection_id}/compilation/runs",
    response_model=CompilationRunResponse,
    status_code=202,
)
async def start_compilation(
    connection_id: uuid.UUID,
    body: CompilationRunCreate,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await compilation_service.start_run(db, connection_id, ctx, options=body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _with_progress(run)


@router.get(
    "/connections/{connection_id}/compilation/runs",
    response_model=list[CompilationRunResponse],
)
async def list_compilation_runs(
    connection_id: uuid.UUID,
    ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    runs = await compilation_service.list_runs(db, connection_id, ctx)
    return [_with_progress(run) for run in runs]


@router.get(
    "/connections/{connection_id}/compilation/runs/{run_id}",
    response_model=CompilationRunResponse,
)
async def get_compilation_run(
    connection_id: uuid.UUID,
    run_id: uuid.UUID,
    ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    run = await compilation_service.get_run(db, run_id, ctx)
    return _with_progress(run)


@router.get(
    "/connections/{connection_id}/compilation/findings",
    response_model=list[CompilationFindingResponse],
)
async def list_compilation_findings(
    connection_id: uuid.UUID,
    status: str | None = None,
    kind: str | None = None,
    ctx: AuthContext = Depends(require_connection_read),
    db: AsyncSession = Depends(get_db),
):
    return await compilation_service.list_findings(db, connection_id, ctx, status, kind)


@router.post(
    "/connections/{connection_id}/compilation/findings/{finding_id}/accept",
    response_model=CompilationFindingResponse,
)
async def accept_finding(
    connection_id: uuid.UUID,
    finding_id: uuid.UUID,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await compilation_service.accept_finding(db, finding_id, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/connections/{connection_id}/compilation/findings/{finding_id}/dismiss",
    response_model=CompilationFindingResponse,
)
async def dismiss_finding(
    connection_id: uuid.UUID,
    finding_id: uuid.UUID,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await compilation_service.dismiss_finding(db, finding_id, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/connections/{connection_id}/compilation/findings/bulk",
    response_model=BulkReviewResponse,
)
async def bulk_review_findings(
    connection_id: uuid.UUID,
    body: BulkReviewRequest,
    ctx: AuthContext = Depends(require_connection_write),
    db: AsyncSession = Depends(get_db),
):
    result = await compilation_service.bulk_review(db, body.finding_ids, body.action, ctx)
    return BulkReviewResponse(**result)
