"""Observability: structured logging, request-ID propagation, Prometheus metrics.

Every optional dependency degrades gracefully — the app boots and serves traffic
whether or not ``structlog`` / ``prometheus_client`` are installed.

* ``configure_logging()`` wires JSON or console logging. When ``structlog`` is
  present it routes both structlog and stdlib (uvicorn) records through one
  formatter; otherwise it falls back to the stdlib logging module.
* ``ObservabilityMiddleware`` assigns/propagates an ``X-Request-ID`` per request,
  binds it into the logging context, times the request, and records Prometheus
  HTTP metrics.
* ``setup_metrics(app)`` mounts ``GET /metrics`` when metrics are enabled.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

REQUEST_ID_HEADER = "X-Request-ID"

# Single source of truth for the current request id, readable everywhere
# (log records, error payloads, background tasks).
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("querywise")


def get_request_id() -> str:
    return request_id_ctx.get()


def bind_request_id(request_id: str | None = None) -> str:
    """Set the request id for the current context, generating one if absent."""
    rid = request_id or uuid.uuid4().hex
    request_id_ctx.set(rid)
    try:
        import structlog

        structlog.contextvars.bind_contextvars(request_id=rid)
    except Exception:  # noqa: BLE001 — structlog optional / not configured
        pass
    return rid


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
class _RequestIdFilter(logging.Filter):
    """Inject the current request id into every stdlib log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class _JsonFormatter(logging.Formatter):
    """Minimal JSON log line — used when structlog is unavailable."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _level() -> int:
    return getattr(logging, settings.log_level.upper(), logging.INFO)


def configure_logging() -> None:
    """Configure root + uvicorn loggers for the chosen format."""
    try:
        _configure_structlog()
    except ImportError:
        _configure_stdlib()


def _configure_stdlib() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(_level())
    # Let uvicorn loggers bubble up to the root handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def _configure_structlog() -> None:
    import structlog

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
    ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(_level())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def get_logger(name: str = "querywise"):
    """Return a structlog logger when available, else a stdlib logger."""
    try:
        import structlog

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Prometheus metrics (optional)
# ---------------------------------------------------------------------------
_REQUESTS = None
_LATENCY = None
_metrics_ready = False


def _init_metrics() -> bool:
    """Create metric objects once. Returns True if Prometheus is available."""
    global _REQUESTS, _LATENCY, _metrics_ready
    if _metrics_ready:
        return _REQUESTS is not None
    _metrics_ready = True
    try:
        from prometheus_client import Counter, Histogram
    except ImportError:
        return False
    _REQUESTS = Counter(
        "querywise_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    _LATENCY = Histogram(
        "querywise_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "path"],
    )
    return True


def _record_request(method: str, path: str, status: int, duration: float) -> None:
    if _REQUESTS is None or _LATENCY is None:
        return
    _REQUESTS.labels(method=method, path=path, status=str(status)).inc()
    _LATENCY.labels(method=method, path=path).observe(duration)


def setup_metrics(app) -> None:
    """Mount GET /metrics if metrics are enabled and prometheus_client is present."""
    if not settings.enable_metrics or not _init_metrics():
        return

    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    async def metrics_endpoint(_request: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.add_route("/metrics", metrics_endpoint, methods=["GET"])


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Per-request correlation id, access logging, and Prometheus metrics."""

    async def dispatch(self, request: Request, call_next):
        rid = bind_request_id(request.headers.get(REQUEST_ID_HEADER))
        start = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.monotonic() - start
            # Use the route template (e.g. /api/v1/query) not the raw path, to
            # keep metric cardinality bounded.
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            _record_request(request.method, path, status, duration)
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                status,
                duration * 1000,
            )
            try:
                response.headers[REQUEST_ID_HEADER] = rid  # type: ignore[name-defined]
            except Exception:  # noqa: BLE001 — request failed before a response
                pass
