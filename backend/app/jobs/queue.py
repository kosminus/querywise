"""Job queue backends.

``JobQueue.submit`` is fire-and-forget: it schedules a registered job by name
and returns immediately (callers run inside the FastAPI event loop). The
in-process backend runs jobs as asyncio tasks on the current loop; the arq
backend enqueues them to Redis for a separate worker process
(``arq app.jobs.worker.WorkerSettings``) to execute.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from app.config import settings
from app.jobs.registry import get_job

logger = logging.getLogger("querywise")


class JobQueue(ABC):
    """Schedules background work decoupled from the request lifecycle."""

    backend_name: str = "base"

    @abstractmethod
    def submit(self, job_name: str, *args: object, name: str | None = None) -> object | None:
        """Schedule the registered job ``job_name`` to run with ``args``.

        Returns a backend-specific handle (an ``asyncio.Task`` for both built-in
        backends) or ``None``.
        """

    async def check(self) -> tuple[bool, str | None]:
        """Readiness check for the backend. Returns ``(ok, detail)``.

        Default backends with no external dependency are always ready; backends
        that depend on external infrastructure (e.g. Redis) override this.
        """
        return True, None


class InProcessJobQueue(JobQueue):
    """Runs jobs as asyncio tasks on the current event loop (default backend)."""

    backend_name = "inprocess"

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def submit(self, job_name: str, *args: object, name: str | None = None) -> asyncio.Task:
        func = get_job(job_name)
        task = asyncio.create_task(self._run(job_name, func, args), name=name or job_name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run(self, job_name: str, func: Callable, args: tuple) -> None:
        try:
            await func(*args)
        except Exception:  # noqa: BLE001 — never let a background job crash silently
            logger.exception("Background job '%s' failed", job_name)


class ArqJobQueue(JobQueue):
    """Enqueues jobs to Redis for an external arq worker to run.

    The Redis pool is created lazily on first submit so constructing the queue
    (e.g. during a health check) never requires Redis or the ``arq`` package.
    """

    backend_name = "arq"

    def __init__(self) -> None:
        self._pool = None
        self._lock = asyncio.Lock()

    def submit(self, job_name: str, *args: object, name: str | None = None) -> asyncio.Task:
        # Schedule the (async) Redis enqueue without blocking the caller.
        return asyncio.create_task(self._enqueue(job_name, args), name=name or job_name)

    async def _enqueue(self, job_name: str, args: tuple) -> None:
        try:
            pool = await self._get_pool()
            await pool.enqueue_job(job_name, *args)
        except Exception:  # noqa: BLE001 — surface via logs, don't crash the request loop
            logger.exception("Failed to enqueue job '%s' to arq/Redis", job_name)

    async def check(self) -> tuple[bool, str | None]:
        """Verify the arq dependency is importable and Redis is reachable."""
        try:
            pool = await self._get_pool()
            await pool.ping()
            return True, None
        except Exception as e:  # noqa: BLE001 — report, don't raise from a probe
            return False, str(e)

    async def _get_pool(self):
        if self._pool is None:
            async with self._lock:
                if self._pool is None:
                    from arq import create_pool
                    from arq.connections import RedisSettings

                    self._pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        return self._pool


_BACKENDS: dict[str, Callable[[], JobQueue]] = {
    "inprocess": InProcessJobQueue,
    "arq": ArqJobQueue,
}

_instance: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Return the process-wide job queue for the configured backend."""
    global _instance
    if _instance is None:
        factory = _BACKENDS.get(settings.job_backend)
        if factory is None:
            raise ValueError(
                f"Unknown job backend '{settings.job_backend}'. Available: {sorted(_BACKENDS)}"
            )
        _instance = factory()
    return _instance


def reset_job_queue() -> None:
    """Clear the cached queue. Primarily a test/reconfiguration hook."""
    global _instance
    _instance = None
