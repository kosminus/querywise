"""Audit-event read API. Admin-only, org-scoped, with CSV export.

Audit writes happen fire-and-forget at call sites via ``audit_service.record``;
this router is the governance read surface over them.
"""

import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.audit_event import AuditEventResponse
from app.core.auth import AuthContext, get_org_context
from app.db.session import get_db
from app.services import audit_service

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=list[AuditEventResponse])
async def list_audit_events(
    event_type: str | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """List the org's audit events, newest first. Requires admin."""
    ctx.require_role("admin")
    events = await audit_service.list_events(
        db,
        organization_id=ctx.organization_id,
        event_type=event_type,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return [AuditEventResponse.model_validate(e) for e in events]


@router.get("/event-types", response_model=list[str])
async def list_event_types(
    ctx: AuthContext = Depends(get_org_context),
):
    """The canonical set of event types, for building a filter UI."""
    ctx.require_role("admin")
    return list(audit_service.EVENT_TYPES)


@router.get("/export")
async def export_audit_events(
    event_type: str | None = Query(None),
    actor_id: uuid.UUID | None = Query(None),
    limit: int = Query(10000, ge=1, le=100000),
    ctx: AuthContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """Export the org's audit events as CSV. Requires admin."""
    ctx.require_role("admin")
    events = await audit_service.list_events(
        db,
        organization_id=ctx.organization_id,
        event_type=event_type,
        actor_id=actor_id,
        limit=limit,
        offset=0,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "event_type", "actor_id", "workspace_id", "created_at", "payload"])
    for e in events:
        writer.writerow(
            [
                str(e.id),
                e.event_type,
                str(e.actor_id) if e.actor_id else "",
                str(e.workspace_id) if e.workspace_id else "",
                e.created_at.isoformat(),
                json.dumps(e.payload, separators=(",", ":")),
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_events.csv"},
    )
