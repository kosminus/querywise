from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db.session import async_session_factory
from app.services.embedding_progress import get_all_progress

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Simple liveness check (kept for backwards compatibility)."""
    return {"status": "ok"}


@router.get("/health/live")
async def liveness():
    """Liveness probe — the process is up and serving requests."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """Readiness probe — verifies dependencies needed to serve traffic.

    Returns 200 when every critical component is healthy, otherwise 503 with a
    per-component breakdown so K8s/load-balancers can route accordingly.
    """
    checks: dict[str, dict] = {}

    # App database — critical.
    checks["database"] = await _check_database()

    # Background job queue — critical (embeddings, future scheduling).
    checks["jobs"] = _check_jobs()

    # LLM + embedding providers — registered/configured, not a live call.
    checks["llm_provider"] = _check_llm_provider()

    critical = ("database", "jobs", "llm_provider")
    healthy = all(checks[name]["status"] == "ok" for name in critical)

    body = {"status": "ok" if healthy else "unavailable", "checks": checks}
    return JSONResponse(status_code=200 if healthy else 503, content=body)


async def _check_database() -> dict:
    try:
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:  # noqa: BLE001 — report, don't crash the probe
        return {"status": "error", "detail": str(e)}


def _check_jobs() -> dict:
    try:
        from app.jobs import get_job_queue

        return {"status": "ok", "backend": get_job_queue().backend_name}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}


def _check_llm_provider() -> dict:
    try:
        from app.llm.provider_registry import get_provider

        get_provider(settings.default_llm_provider)
        return {"status": "ok", "provider": settings.default_llm_provider}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}


@router.get("/embeddings/status")
async def embedding_status():
    """Return embedding generation progress for all connections."""
    progress = get_all_progress()
    return {
        "tasks": [
            {
                "connection_id": p.connection_id,
                "status": p.status,
                "total": p.total,
                "completed": p.completed,
                "error": p.error,
            }
            for p in progress.values()
        ]
    }
