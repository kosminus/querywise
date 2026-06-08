import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.rate_limit import install_rate_limiting
from app.core.telemetry import (
    ObservabilityMiddleware,
    configure_logging,
    configure_tracing,
    setup_metrics,
)
from app.db.session import engine

logger = logging.getLogger("querywise")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure vector columns match configured dimension
    from app.services.setup_service import ensure_embedding_dimensions

    await ensure_embedding_dimensions()

    if settings.auto_setup_sample_db:
        from app.services.setup_service import auto_setup_sample_db

        await auto_setup_sample_db()

    # Start the recurring-report scheduler loop (registers "run_schedule").
    from app.jobs.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    yield
    # Shutdown
    await stop_scheduler()
    await engine.dispose()


def create_app() -> FastAPI:
    configure_logging()
    configure_tracing()

    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        lifespan=lifespan,
    )

    # Middleware runs in reverse order of registration; add observability last
    # so it wraps everything (assigns the request id seen by all other layers).
    install_rate_limiting(app, settings.api_prefix)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ObservabilityMiddleware)

    register_exception_handlers(app)
    setup_metrics(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    # Mount QueryWise as an MCP server at /mcp (streamable HTTP).
    # Lets Claude and other MCP clients reach the same tools the REST API uses:
    #   claude mcp add --transport http querywise http://localhost:8000/mcp
    from app.mcp import mount_mcp

    mount_mcp(app)

    return app


app = create_app()
