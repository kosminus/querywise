"""arq worker entrypoint.

Run with::

    JOB_BACKEND=arq arq app.jobs.worker.WorkerSettings

The worker consumes jobs enqueued by ``ArqJobQueue`` and executes the same
registered coroutine functions the in-process backend would run — so switching
``JOB_BACKEND`` between ``inprocess`` and ``arq`` requires no code changes.

This module is only imported by the arq CLI, so it may import ``arq`` directly.
"""

from __future__ import annotations

from arq import func
from arq.connections import RedisSettings

import app.jobs.tasks  # noqa: F401 — populate the job registry in this process
from app.config import settings
from app.jobs.registry import registered_jobs


def _build_functions() -> list:
    """Wrap each registered job as an arq task (dropping arq's ctx arg)."""
    functions = []
    for name, job in registered_jobs().items():

        async def _runner(ctx, *args, _job=job):  # noqa: ARG001 — arq passes ctx
            await _job(*args)

        functions.append(func(_runner, name=name))
    return functions


class WorkerSettings:
    functions = _build_functions()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
