import os

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

    # Background job queue — critical (embeddings, future scheduling). For the
    # arq backend this pings Redis, so a misconfigured queue fails readiness
    # instead of silently dropping enqueued jobs later.
    checks["jobs"] = await _check_jobs()

    # Chat LLM provider used for SQL generation.
    checks["llm_provider"] = _check_llm_provider()

    # Embedding provider — distinct from the chat provider (e.g. the default
    # Anthropic setup resolves embeddings to OpenAI). Embedding generation
    # fails without its own credentials, so check it explicitly.
    checks["embedding_provider"] = _check_embedding_provider()

    critical = ("database", "jobs", "llm_provider", "embedding_provider")
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


async def _check_jobs() -> dict:
    try:
        from app.jobs import get_job_queue

        queue = get_job_queue()
        ok, detail = await queue.check()
        result = {"status": "ok" if ok else "error", "backend": queue.backend_name}
        if detail:
            result["detail"] = detail
        return result
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}


def _credential_issue(provider_type: str) -> str | None:
    """Return a human-readable reason if the provider's credential is absent."""
    if provider_type == "openai":
        return None if os.environ.get("OPENAI_API_KEY") else "OPENAI_API_KEY not set"
    if provider_type == "anthropic":
        return None if os.environ.get("ANTHROPIC_API_KEY") else "ANTHROPIC_API_KEY not set"
    if provider_type == "azure_openai":
        has_key = settings.azure_openai_api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        return None if has_key else "AZURE_OPENAI_API_KEY not set"
    # ollama (and any future local provider) needs no API key.
    return None


def _provider_status(provider) -> dict:
    ptype = provider.provider_type.value
    issue = _credential_issue(ptype)
    if issue:
        return {"status": "error", "provider": ptype, "detail": issue}
    return {"status": "ok", "provider": ptype}


def _check_llm_provider() -> dict:
    try:
        from app.llm.provider_registry import get_provider

        return _provider_status(get_provider(settings.default_llm_provider))
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)}


def _check_embedding_provider() -> dict:
    try:
        from app.llm.provider_registry import get_embedding_provider

        return _provider_status(get_embedding_provider())
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
