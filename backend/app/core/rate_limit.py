"""In-memory sliding-window rate limiting.

Enforces ``settings.max_queries_per_minute`` (previously defined but never
wired up) on the query endpoints. The limiter is per-process and keyed by
client identity (API key / forwarded IP / peer address); for multi-replica
deployments swap the store for Redis behind the same ``RateLimiter`` interface.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


class SlidingWindowRateLimiter:
    """Allows at most ``max_requests`` per ``window_seconds`` per key."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, int, float]:
        """Record a hit for ``key``.

        Returns ``(allowed, remaining, retry_after_seconds)``.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_requests:
                retry_after = self.window_seconds - (now - hits[0])
                return False, 0, max(retry_after, 0.0)

            hits.append(now)
            return True, self.max_requests - len(hits), 0.0


def path_in_scope(path: str, prefix: str) -> bool:
    """True if ``path`` is the prefix itself or a child of it.

    Uses a segment-aware match so the query-execution prefix (``/api/v1/query``)
    does not accidentally also limit sibling routes like ``/api/v1/query-history``.
    """
    return path == prefix or path.startswith(prefix + "/")


def _client_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"key:{api_key}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting to NL/SQL query endpoints under ``/query``."""

    def __init__(self, app, limiter: SlidingWindowRateLimiter, path_prefix: str) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._path_prefix = path_prefix

    async def dispatch(self, request: Request, call_next):
        if not path_in_scope(request.url.path, self._path_prefix):
            return await call_next(request)

        allowed, remaining, retry_after = await self._limiter.check(_client_key(request))
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": (
                        f"Rate limit exceeded: max {self._limiter.max_requests} "
                        f"queries per minute. Try again in {retry_after:.0f}s."
                    )
                },
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def install_rate_limiting(app, api_prefix: str) -> None:
    """Wire the query rate limiter onto the app when enabled."""
    if not settings.rate_limit_enabled:
        return
    limiter = SlidingWindowRateLimiter(max_requests=settings.max_queries_per_minute)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        path_prefix=f"{api_prefix}/query",
    )
