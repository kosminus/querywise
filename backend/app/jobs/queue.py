"""Job queue backends.

``JobQueue.submit`` is fire-and-forget: it schedules a coroutine factory to run
and returns immediately. The in-process backend keeps strong references to
running tasks so they are not garbage-collected mid-flight (a common
``asyncio.create_task`` footgun).
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.config import settings

logger = logging.getLogger("querywise")

CoroFactory = Callable[[], Awaitable[None]]


class JobQueue(ABC):
    """Schedules background work decoupled from the request lifecycle."""

    backend_name: str = "base"

    @abstractmethod
    def submit(self, factory: CoroFactory, *, name: str | None = None) -> object | None:
        """Schedule ``factory()`` to run in the background.

        Returns a backend-specific handle (an ``asyncio.Task`` for the
        in-process backend) or ``None``.
        """


class InProcessJobQueue(JobQueue):
    """Runs jobs as asyncio tasks on the current event loop (default backend)."""

    backend_name = "inprocess"

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def submit(self, factory: CoroFactory, *, name: str | None = None) -> asyncio.Task:
        task = asyncio.create_task(self._run(factory, name), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run(self, factory: CoroFactory, name: str | None) -> None:
        try:
            await factory()
        except Exception:  # noqa: BLE001 — never let a background job crash silently
            logger.exception("Background job '%s' failed", name or "<unnamed>")


def _build_arq() -> JobQueue:
    raise NotImplementedError(
        "JOB_BACKEND=arq is not yet wired up. Install the 'jobs' extra "
        "(pip install -e '.[jobs]'), run an arq worker against REDIS_URL, and "
        "register an ArqJobQueue here. Use JOB_BACKEND=inprocess until then."
    )


_BACKENDS: dict[str, Callable[[], JobQueue]] = {
    "inprocess": InProcessJobQueue,
    "arq": _build_arq,
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
