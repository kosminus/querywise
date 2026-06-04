"""Background job runner abstraction.

Phase 0 of the platform roadmap introduces a durable-job seam so that
embedding generation, long-running queries, and (later) scheduled reports run
through one interface instead of bare ``asyncio.create_task`` calls.

The default ``inprocess`` backend preserves today's behaviour exactly (fire-and-
forget asyncio tasks, suitable for single-process deploys). Swapping
``JOB_BACKEND=arq`` (Redis) is the upgrade path for multi-replica deployments.
"""

from app.jobs.queue import JobQueue, get_job_queue, reset_job_queue

__all__ = ["JobQueue", "get_job_queue", "reset_job_queue"]
