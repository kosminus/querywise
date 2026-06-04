"""Named-job registry.

Backends like arq run jobs in a *separate worker process*, so a job must be
identified by a stable name (not an in-process closure). Jobs register a name →
coroutine-function mapping here; both the in-process queue and the arq worker
resolve jobs through it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

JobFunc = Callable[..., Awaitable[None]]

_JOB_FUNCTIONS: dict[str, JobFunc] = {}


def register_job(name: str, func: JobFunc) -> JobFunc:
    """Register ``func`` under ``name`` (idempotent)."""
    _JOB_FUNCTIONS[name] = func
    return func


def get_job(name: str) -> JobFunc:
    try:
        return _JOB_FUNCTIONS[name]
    except KeyError:
        raise KeyError(
            f"No job registered under '{name}'. Registered: {sorted(_JOB_FUNCTIONS)}"
        ) from None


def registered_jobs() -> dict[str, JobFunc]:
    return dict(_JOB_FUNCTIONS)
