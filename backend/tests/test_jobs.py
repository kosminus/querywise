import asyncio

import pytest

from app.jobs import get_job_queue, reset_job_queue
from app.jobs.queue import InProcessJobQueue


def test_default_backend_is_inprocess():
    queue = get_job_queue()
    assert queue.backend_name == "inprocess"
    assert isinstance(queue, InProcessJobQueue)


async def test_submit_runs_job():
    queue = InProcessJobQueue()
    ran = asyncio.Event()

    async def job():
        ran.set()

    task = queue.submit(job, name="t")
    await asyncio.wait_for(task, timeout=1)
    assert ran.is_set()


async def test_job_failure_is_swallowed(caplog):
    queue = InProcessJobQueue()

    async def boom():
        raise RuntimeError("kaboom")

    task = queue.submit(boom, name="boom")
    await asyncio.wait_for(task, timeout=1)
    # Task completed (did not propagate) and the failure was logged.
    assert task.done()
    assert task.exception() is None
    assert "boom" in caplog.text or "kaboom" in caplog.text


async def test_tasks_are_tracked_until_done():
    queue = InProcessJobQueue()
    release = asyncio.Event()

    async def job():
        await release.wait()

    task = queue.submit(job, name="held")
    assert task in queue._tasks
    release.set()
    await asyncio.wait_for(task, timeout=1)
    assert task not in queue._tasks


def test_unknown_backend_raises(monkeypatch):
    import app.jobs.queue as q

    reset_job_queue()
    monkeypatch.setattr(q.settings, "job_backend", "nope")
    with pytest.raises(ValueError, match="Unknown job backend"):
        get_job_queue()


def test_arq_backend_not_implemented(monkeypatch):
    import app.jobs.queue as q

    reset_job_queue()
    monkeypatch.setattr(q.settings, "job_backend", "arq")
    with pytest.raises(NotImplementedError):
        get_job_queue()
