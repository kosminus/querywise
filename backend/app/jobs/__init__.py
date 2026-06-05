"""Background job runner abstraction.

Phase 0 of the platform roadmap introduces a durable-job seam so that
embedding generation, long-running queries, and (later) scheduled reports run
through one interface instead of bare ``asyncio.create_task`` calls.

* ``inprocess`` (default) — fire-and-forget asyncio tasks; single-process.
* ``arq`` (Redis) — enqueue to a separate worker process for multi-replica
  deployments. Run the worker with ``arq app.jobs.worker.WorkerSettings``.

Jobs are referenced by name (see ``app.jobs.registry``) so they can cross the
process boundary to the arq worker.
"""

from app.jobs.queue import JobQueue, get_job_queue, reset_job_queue
from app.jobs.registry import get_job, register_job, registered_jobs

__all__ = [
    "JobQueue",
    "get_job_queue",
    "reset_job_queue",
    "register_job",
    "get_job",
    "registered_jobs",
]
