"""In-process scheduler loop for recurring reports.

A single asyncio loop (started from the FastAPI lifespan) ticks every
``SCHEDULER_TICK_SECONDS``, atomically claims due schedules, and dispatches a
``run_schedule`` job per schedule through the job queue. The claim advances
``next_run_at`` to the next cron slot *before* dispatching, using
``FOR UPDATE SKIP LOCKED`` — so concurrent ticks (or multiple replicas) never
double-fire the same schedule, and a worker crash skips at most one run rather
than stalling or looping.

Dispatch goes through ``get_job_queue()``, so under ``JOB_BACKEND=arq`` the
report runs in the worker process while this loop only does the claiming.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.db.models.schedule import Schedule
from app.db.session import async_session_factory
from app.jobs import get_job_queue, register_job

logger = logging.getLogger("querywise")


async def run_schedule_job(schedule_id: str) -> None:
    """Job body: load one schedule and run it end-to-end (own session)."""
    from app.services import schedule_service

    async with async_session_factory() as db:
        try:
            schedule = await db.get(Schedule, uuid.UUID(str(schedule_id)))
            if schedule is None:
                logger.warning("run_schedule: schedule %s not found", schedule_id)
                return
            # next_run_at was already advanced by the claim, so don't reschedule.
            await schedule_service.run_one(db, schedule, reschedule=False)
            await db.commit()
        except Exception:  # noqa: BLE001 — never crash the worker
            await db.rollback()
            logger.exception("run_schedule: schedule %s failed", schedule_id)


register_job("run_schedule", run_schedule_job)


async def _claim_and_dispatch() -> int:
    """Claim due schedules (advancing next_run_at) and dispatch their jobs."""
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        from app.services import schedule_service

        result = await db.execute(
            select(Schedule)
            .where(
                Schedule.enabled.is_(True),
                Schedule.next_run_at.isnot(None),
                Schedule.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        due = list(result.scalars().all())
        claimed: list[str] = []
        for s in due:
            s.next_run_at = schedule_service.compute_next_run(s.cron, after=now)
            claimed.append(str(s.id))
        await db.commit()

    if claimed:
        queue = get_job_queue()
        for sid in claimed:
            queue.submit("run_schedule", sid, name=f"schedule-{sid}")
        logger.info("Scheduler dispatched %d due schedule(s)", len(claimed))
    return len(claimed)


_task: asyncio.Task | None = None


async def _loop() -> None:
    interval = max(5, settings.scheduler_tick_seconds)
    while True:
        try:
            await _claim_and_dispatch()
        except Exception:  # noqa: BLE001 — a bad tick must not kill the loop
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(interval)


def start_scheduler() -> None:
    """Start the scheduler loop (no-op if disabled or already running)."""
    global _task
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop(), name="scheduler-loop")
    logger.info("Scheduler started (tick=%ss)", settings.scheduler_tick_seconds)


async def stop_scheduler() -> None:
    """Cancel the scheduler loop on shutdown."""
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
