"""Append-only audit log of security- and governance-relevant actions.

``record`` is **fire-and-forget**: it is wrapped so that a failure to write an
audit row never propagates into — and never fails — the action being audited.
This is a deliberate trade-off: an audit miss is logged but tolerated, whereas a
broken login or blocked-query path is not.

Events are written inline (a small INSERT on the request's own session) rather
than through the job queue, so they are durable the moment the request commits
and need no running worker. The write uses a *nested* transaction (SAVEPOINT) so
that an audit failure can be rolled back without poisoning the caller's outer
transaction.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telemetry import get_request_id
from app.db.models.audit_event import AuditEvent

logger = logging.getLogger("uvicorn.error")

# --- Canonical event types --------------------------------------------------
# Dotted "<subject>.<verb>" names. Keep this list authoritative so the API can
# expose it as a filter facet and call sites don't drift into typos.
AUTH_LOGIN = "auth.login"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_MAGIC_LINK_REQUESTED = "auth.magic_link_requested"
AUTH_LOGOUT = "auth.logout"

CONNECTION_CREATED = "connection.created"
CONNECTION_UPDATED = "connection.updated"
CONNECTION_DELETED = "connection.deleted"
CONNECTION_INTROSPECTED = "connection.introspected"
CREDENTIAL_ROTATED = "connection.credential_rotated"

QUERY_GENERATED = "query.generated"
QUERY_EXECUTED = "query.executed"
QUERY_BLOCKED = "query.blocked"

METRIC_CERTIFIED = "metric.certified"
KNOWLEDGE_IMPORTED = "knowledge.imported"

SCHEDULE_CREATED = "schedule.created"
SCHEDULE_UPDATED = "schedule.updated"
SCHEDULE_DELETED = "schedule.deleted"
SCHEDULE_RUN = "schedule.run"
REPORT_DELIVERED = "report.delivered"

POLICY_CREATED = "policy.created"
POLICY_UPDATED = "policy.updated"
POLICY_DELETED = "policy.deleted"

EVENT_TYPES: tuple[str, ...] = (
    AUTH_LOGIN,
    AUTH_LOGIN_FAILED,
    AUTH_MAGIC_LINK_REQUESTED,
    AUTH_LOGOUT,
    CONNECTION_CREATED,
    CONNECTION_UPDATED,
    CONNECTION_DELETED,
    CONNECTION_INTROSPECTED,
    CREDENTIAL_ROTATED,
    QUERY_GENERATED,
    QUERY_EXECUTED,
    QUERY_BLOCKED,
    METRIC_CERTIFIED,
    KNOWLEDGE_IMPORTED,
    SCHEDULE_CREATED,
    SCHEDULE_UPDATED,
    SCHEDULE_DELETED,
    SCHEDULE_RUN,
    REPORT_DELIVERED,
    POLICY_CREATED,
    POLICY_UPDATED,
    POLICY_DELETED,
)


async def record(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_type: str,
    actor_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Write one audit event. Never raises.

    The caller is responsible for committing its own transaction; this adds the
    event to the session within a SAVEPOINT so a write failure is isolated. The
    current request id (if any) is folded into the payload for correlation.
    """

    data = dict(payload or {})
    rid = get_request_id()
    if rid and rid != "-":
        data.setdefault("request_id", rid)

    event = AuditEvent(
        organization_id=organization_id,
        event_type=event_type,
        actor_id=actor_id,
        workspace_id=workspace_id,
        payload=data,
    )
    try:
        async with db.begin_nested():
            db.add(event)
    except Exception:  # noqa: BLE001 — auditing must never break the caller
        logger.warning("Failed to record audit event '%s'", event_type, exc_info=True)


async def list_events(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_type: str | None = None,
    actor_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    """Return an org's audit events, newest first, with optional filters."""

    stmt = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())
