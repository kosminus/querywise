import asyncio

import pytest

from app.jobs import get_job_queue, register_job, reset_job_queue
from app.jobs.queue import ArqJobQueue, InProcessJobQueue
from app.jobs.registry import _JOB_FUNCTIONS, get_job, registered_jobs


def test_default_backend_is_inprocess():
    queue = get_job_queue()
    assert queue.backend_name == "inprocess"
    assert isinstance(queue, InProcessJobQueue)


# --- registry -------------------------------------------------------------
def test_register_and_get_job():
    async def noop():
        return None

    register_job("unit-test-job", noop)
    assert get_job("unit-test-job") is noop
    assert "unit-test-job" in registered_jobs()
    _JOB_FUNCTIONS.pop("unit-test-job", None)


def test_get_unknown_job_raises():
    with pytest.raises(KeyError, match="No job registered"):
        get_job("nope-not-a-job")


# --- in-process backend ---------------------------------------------------
async def test_submit_runs_registered_job():
    ran = asyncio.Event()

    async def job():
        ran.set()

    register_job("runs", job)
    task = InProcessJobQueue().submit("runs", name="t")
    await asyncio.wait_for(task, timeout=1)
    assert ran.is_set()
    _JOB_FUNCTIONS.pop("runs", None)


async def test_submit_passes_args():
    seen = {}

    async def job(a, b):
        seen["a"], seen["b"] = a, b

    register_job("with-args", job)
    task = InProcessJobQueue().submit("with-args", 1, "two")
    await asyncio.wait_for(task, timeout=1)
    assert seen == {"a": 1, "b": "two"}
    _JOB_FUNCTIONS.pop("with-args", None)


async def test_submit_unknown_job_raises_immediately():
    with pytest.raises(KeyError):
        InProcessJobQueue().submit("definitely-missing")


async def test_job_failure_is_swallowed(caplog):
    async def boom():
        raise RuntimeError("kaboom")

    register_job("boom", boom)
    task = InProcessJobQueue().submit("boom", name="boom")
    await asyncio.wait_for(task, timeout=1)
    assert task.done()
    assert task.exception() is None
    assert "boom" in caplog.text or "kaboom" in caplog.text
    _JOB_FUNCTIONS.pop("boom", None)


async def test_tasks_are_tracked_until_done():
    release = asyncio.Event()

    async def job():
        await release.wait()

    register_job("held", job)
    queue = InProcessJobQueue()
    task = queue.submit("held", name="held")
    assert task in queue._tasks
    release.set()
    await asyncio.wait_for(task, timeout=1)
    assert task not in queue._tasks
    _JOB_FUNCTIONS.pop("held", None)


# --- backend selection ----------------------------------------------------
def test_unknown_backend_raises(monkeypatch):
    import app.jobs.queue as q

    reset_job_queue()
    monkeypatch.setattr(q.settings, "job_backend", "nope")
    with pytest.raises(ValueError, match="Unknown job backend"):
        get_job_queue()


def test_arq_backend_selected(monkeypatch):
    import app.jobs.queue as q

    reset_job_queue()
    monkeypatch.setattr(q.settings, "job_backend", "arq")
    queue = get_job_queue()
    assert isinstance(queue, ArqJobQueue)
    assert queue.backend_name == "arq"


async def test_arq_submit_swallows_enqueue_errors(caplog):
    # If Redis is unreachable the enqueue must fail gracefully (logged),
    # never propagating out of the fire-and-forget task.
    queue = ArqJobQueue()

    async def boom_pool():
        raise ConnectionError("redis down")

    queue._get_pool = boom_pool  # type: ignore[method-assign]
    task = queue.submit("generate_embeddings", "some-id")
    await asyncio.wait_for(task, timeout=2)
    assert task.exception() is None
    assert "Failed to enqueue" in caplog.text


def test_embeddings_job_is_registered():
    # Importing setup_service (done transitively) registers the embeddings job.
    import app.services.setup_service  # noqa: F401

    assert "generate_embeddings" in registered_jobs()
