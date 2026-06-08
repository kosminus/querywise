"""Scheduled reports — CRUD, cron math, and the run/deliver pipeline.

A schedule runs a saved query (or dashboard) on a cron cadence and delivers the
result over a notification channel, optionally only when a threshold is met.

Workspace-scoped like dashboards. Runs are executed by the scheduler under a
system-built :class:`AuthContext` for the schedule's own workspace (so the
saved query's connection auth + result cache still apply), not the request user.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import AuthContext
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.dashboard import Dashboard
from app.db.models.membership import ROLE_ADMIN, ROLE_EDITOR
from app.db.models.saved_query import SavedQuery
from app.db.models.schedule import (
    STATUS_ERROR,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    TARGET_SAVED_QUERY,
    TARGET_TYPES,
    Schedule,
)
from app.db.models.user import User
from app.notifications import get_notifier
from app.notifications.base import NotificationMessage
from app.services import audit_service, saved_query_service

logger = logging.getLogger("querywise")

_REPORT_ROW_LIMIT = 100  # rows rendered into a delivered report


# --------------------------------------------------------------------------- #
# Cron
# --------------------------------------------------------------------------- #
def compute_next_run(cron: str, after: datetime | None = None) -> datetime | None:
    """Next fire time (UTC) for ``cron`` strictly after ``after`` (or now).

    Uses ``croniter`` (the optional ``[scheduling]`` extra); returns None and
    logs if it isn't installed, so the rest of the feature degrades gracefully.
    """
    try:
        from croniter import croniter
    except ImportError:
        logger.warning(
            "croniter not installed — install the [scheduling] extra for cron "
            "scheduling; schedule '%s' will not auto-run",
            cron,
        )
        return None
    base = after or datetime.now(UTC)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return croniter(cron, base).get_next(datetime)


def validate_cron(cron: str) -> None:
    """Raise ValidationError if ``cron`` is malformed (no-op without croniter)."""
    try:
        from croniter import croniter
    except ImportError:
        return
    if not croniter.is_valid(cron):
        raise ValidationError(f"Invalid cron expression: {cron!r}")


# --------------------------------------------------------------------------- #
# Threshold
# --------------------------------------------------------------------------- #
_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate_threshold(threshold: dict | None, result: dict) -> bool | None:
    """Return whether ``threshold`` is met by ``result``; None if not applicable.

    ``threshold`` = ``{"metric": "row_count"|"<column>", "op": ">", "value": N}``.
    For a column metric the first row's value in that column is compared.
    """
    if not threshold:
        return None
    op = _OPS.get(threshold.get("op", ">"))
    if op is None:
        return None
    target = threshold.get("value")
    metric = threshold.get("metric", "row_count")

    if metric == "row_count":
        actual: Any = result.get("row_count", 0)
    else:
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        if metric not in columns or not rows:
            return None
        actual = rows[0][columns.index(metric)]

    try:
        return op(actual, target)
    except TypeError:
        return None


# --------------------------------------------------------------------------- #
# Access + CRUD (mirrors dashboard_service)
# --------------------------------------------------------------------------- #
def _assert_access(schedule: Schedule, ctx: AuthContext, *, write: bool = False) -> None:
    if (
        schedule.organization_id != ctx.organization_id
        or schedule.workspace_id != ctx.workspace_id
    ):
        raise NotFoundError("Schedule", str(schedule.id))
    if write:
        ctx.require_role(ROLE_EDITOR)


async def _load(
    db: AsyncSession, schedule_id: uuid.UUID, ctx: AuthContext, *, write: bool = False
) -> Schedule:
    schedule = await db.get(Schedule, schedule_id)
    if schedule is None:
        raise NotFoundError("Schedule", str(schedule_id))
    _assert_access(schedule, ctx, write=write)
    return schedule


async def list_schedules(db: AsyncSession, ctx: AuthContext) -> list[Schedule]:
    result = await db.execute(
        select(Schedule)
        .where(
            Schedule.organization_id == ctx.organization_id,
            Schedule.workspace_id == ctx.workspace_id,
        )
        .order_by(Schedule.created_at.desc())
    )
    return list(result.scalars().all())


async def get_schedule(db: AsyncSession, schedule_id: uuid.UUID, ctx: AuthContext) -> Schedule:
    return await _load(db, schedule_id, ctx)


async def create_schedule(db: AsyncSession, ctx: AuthContext, **data: Any) -> Schedule:
    ctx.require_role(ROLE_EDITOR)
    target_type = data.get("target_type")
    if target_type not in TARGET_TYPES:
        raise ValidationError(f"target_type must be one of {TARGET_TYPES}")
    validate_cron(data["cron"])
    await _assert_target_exists(db, ctx, target_type, data["target_id"])

    schedule = Schedule(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        owner_id=ctx.user_id,
        **data,
    )
    if schedule.enabled:
        schedule.next_run_at = compute_next_run(schedule.cron)
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    await audit_service.record(
        db,
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.SCHEDULE_CREATED,
        payload={"schedule_id": str(schedule.id), "name": schedule.name, "cron": schedule.cron},
    )
    return schedule


async def update_schedule(
    db: AsyncSession, schedule_id: uuid.UUID, ctx: AuthContext, updates: dict[str, Any]
) -> Schedule:
    schedule = await _load(db, schedule_id, ctx, write=True)
    if "cron" in updates and updates["cron"]:
        validate_cron(updates["cron"])
    for key, value in updates.items():
        setattr(schedule, key, value)
    # Recompute the next fire time when cadence or enabled state changes.
    schedule.next_run_at = compute_next_run(schedule.cron) if schedule.enabled else None
    await db.flush()
    await db.refresh(schedule)
    await audit_service.record(
        db,
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.SCHEDULE_UPDATED,
        payload={"schedule_id": str(schedule.id), "name": schedule.name},
    )
    return schedule


async def delete_schedule(db: AsyncSession, schedule_id: uuid.UUID, ctx: AuthContext) -> None:
    schedule = await _load(db, schedule_id, ctx, write=True)
    name = schedule.name
    await db.delete(schedule)
    await db.flush()
    await audit_service.record(
        db,
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user_id,
        event_type=audit_service.SCHEDULE_DELETED,
        payload={"schedule_id": str(schedule_id), "name": name},
    )


async def _assert_target_exists(
    db: AsyncSession, ctx: AuthContext, target_type: str, target_id: uuid.UUID
) -> None:
    model = SavedQuery if target_type == TARGET_SAVED_QUERY else Dashboard
    obj = await db.get(model, target_id)
    if obj is None or obj.organization_id != ctx.organization_id:
        raise NotFoundError(target_type, str(target_id))


# --------------------------------------------------------------------------- #
# Run + deliver
# --------------------------------------------------------------------------- #
async def context_for_schedule(db: AsyncSession, schedule: Schedule) -> AuthContext:
    """Build a system AuthContext bound to the schedule's own workspace.

    The owner (if still present) is the actor so the run's snapshots + query
    audit attribute correctly; falls back to the bootstrapped admin.
    """
    actor: User | None = None
    if schedule.owner_id:
        actor = await db.get(User, schedule.owner_id)
    if actor is None:
        from app.services import identity_service

        _, _, actor = await identity_service.bootstrap_default_identity(db)
    return AuthContext(
        user=actor,
        organization_id=schedule.organization_id,
        workspace_id=schedule.workspace_id,
        role=ROLE_ADMIN,
    )


async def _run_target(db: AsyncSession, schedule: Schedule, ctx: AuthContext) -> dict:
    """Execute the schedule's target and return a normalized result dict."""
    if schedule.target_type == TARGET_SAVED_QUERY:
        saved = await db.get(SavedQuery, schedule.target_id)
        if saved is None or saved.organization_id != ctx.organization_id:
            raise NotFoundError("SavedQuery", str(schedule.target_id))
        result = await saved_query_service.run_saved_query(
            db, saved, ctx, supplied_params=schedule.params, refresh=True
        )
        return {"title": saved.name, **result, "sections": [{"name": saved.name, **result}]}

    # Dashboard: run every tile's saved query, collect a section per tile.
    dashboard = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == schedule.target_id)
        .options(selectinload(Dashboard.tiles))
    )
    dash = dashboard.scalar_one_or_none()
    if dash is None or dash.organization_id != ctx.organization_id:
        raise NotFoundError("Dashboard", str(schedule.target_id))

    sections = []
    total_rows = 0
    for tile in dash.tiles:
        saved = await db.get(SavedQuery, tile.saved_query_id)
        if saved is None:
            continue
        res = await saved_query_service.run_saved_query(
            db, saved, ctx, supplied_params=schedule.params, refresh=True
        )
        total_rows += res.get("row_count", 0)
        sections.append({"name": tile.title or saved.name, **res})
    return {"title": dash.name, "row_count": total_rows, "sections": sections}


def _render_report(schedule: Schedule, result: dict, threshold_met: bool | None) -> tuple[str, str]:
    """Return (text_body, html_body) for the delivered report."""
    lines = [f"Report: {schedule.name}", f"Target: {result.get('title', '')}", ""]
    html_parts = [f"<h2>{schedule.name}</h2>"]
    if threshold_met is not None:
        flag = "MET" if threshold_met else "not met"
        lines.append(f"Threshold {flag}: {schedule.threshold}")
        html_parts.append(f"<p><b>Threshold {flag}:</b> {schedule.threshold}</p>")

    for section in result.get("sections", []):
        columns = section.get("columns") or []
        rows = (section.get("rows") or [])[:_REPORT_ROW_LIMIT]
        lines.append(f"\n## {section['name']} — {section.get('row_count', 0)} rows")
        lines.append("\t".join(str(c) for c in columns))
        for row in rows:
            lines.append("\t".join("" if v is None else str(v) for v in row))

        html_parts.append(f"<h3>{section['name']} — {section.get('row_count', 0)} rows</h3>")
        head = "".join(f"<th>{c}</th>" for c in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{'' if v is None else v}</td>" for v in row) + "</tr>"
            for row in rows
        )
        html_parts.append(
            f"<table border='1' cellpadding='4' cellspacing='0'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        )
    return "\n".join(lines), "\n".join(html_parts)


async def run_one(db: AsyncSession, schedule: Schedule, *, reschedule: bool = True) -> dict:
    """Execute one schedule end-to-end: run target → threshold → deliver.

    Updates ``last_*`` and (when ``reschedule``) ``next_run_at``. Returns a
    summary dict. Raises only on a target-execution error after recording it.
    """
    ctx = await context_for_schedule(db, schedule)
    now = datetime.now(UTC)
    delivered = False
    threshold_met: bool | None = None
    status = STATUS_SUCCESS
    error: str | None = None

    try:
        result = await _run_target(db, schedule, ctx)
        threshold_met = evaluate_threshold(schedule.threshold, result)

        suppress = schedule.only_on_threshold and threshold_met is False
        if suppress:
            status = STATUS_SKIPPED
        else:
            text_body, html_body = _render_report(schedule, result, threshold_met)
            subject = f"[QueryWise] {schedule.name}"
            if threshold_met:
                subject = f"[QueryWise] ⚠ {schedule.name} — threshold met"
            await get_notifier(schedule.channel).send(
                NotificationMessage(
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    recipients=list(schedule.recipients or []),
                )
            )
            delivered = True
    except Exception as e:  # noqa: BLE001 — record the failure on the schedule
        status = STATUS_ERROR
        error = str(e)
        logger.exception("Schedule '%s' run failed", schedule.id)

    schedule.last_run_at = now
    schedule.last_status = status
    schedule.last_error = error
    if reschedule and schedule.enabled:
        schedule.next_run_at = compute_next_run(schedule.cron, after=now)
    await db.flush()

    await audit_service.record(
        db,
        organization_id=schedule.organization_id,
        workspace_id=schedule.workspace_id,
        actor_id=schedule.owner_id,
        event_type=audit_service.REPORT_DELIVERED if delivered else audit_service.SCHEDULE_RUN,
        payload={
            "schedule_id": str(schedule.id),
            "name": schedule.name,
            "channel": schedule.channel,
            "status": status,
            "delivered": delivered,
            "threshold_met": threshold_met,
            "error": error,
        },
    )
    return {
        "schedule_id": schedule.id,
        "status": status,
        "delivered": delivered,
        "threshold_met": threshold_met,
        "error": error,
    }


async def run_now(db: AsyncSession, schedule_id: uuid.UUID, ctx: AuthContext) -> dict:
    """Manually trigger a schedule (does not change its cron cadence)."""
    schedule = await _load(db, schedule_id, ctx, write=True)
    return await run_one(db, schedule, reschedule=False)
