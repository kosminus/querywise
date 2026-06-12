"""In-memory progress tracker for semantic-compiler runs (mirrors embedding_progress)."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class CompilationProgress:
    connection_id: str
    total: int = 0
    completed: int = 0
    stage: str = ""  # human-readable current stage
    status: str = "pending"  # pending | running | completed | failed
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


_progress: dict[str, CompilationProgress] = {}
_tasks: dict[str, asyncio.Task] = {}


def start_tracking(connection_id: str, total: int) -> CompilationProgress:
    p = CompilationProgress(
        connection_id=connection_id,
        total=total,
        status="running",
        started_at=datetime.now(UTC),
    )
    _progress[connection_id] = p
    return p


def advance(connection_id: str, stage: str) -> None:
    if connection_id in _progress:
        p = _progress[connection_id]
        p.completed += 1
        p.stage = stage


def mark_completed(connection_id: str) -> None:
    if connection_id in _progress:
        p = _progress[connection_id]
        p.status = "completed"
        p.completed = p.total
        p.finished_at = datetime.now(UTC)


def mark_failed(connection_id: str, error: str) -> None:
    if connection_id in _progress:
        p = _progress[connection_id]
        p.status = "failed"
        p.error = error
        p.finished_at = datetime.now(UTC)


def get_progress(connection_id: str) -> CompilationProgress | None:
    return _progress.get(connection_id)


def is_running(connection_id: str) -> bool:
    return connection_id in _progress and _progress[connection_id].status == "running"


def register_task(connection_id: str, task: asyncio.Task) -> None:
    """Store task reference to prevent garbage collection (in-process queue only)."""
    _tasks[connection_id] = task
