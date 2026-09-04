"""Fixed-window rate limiting middleware.

Why fixed-window and not a token bucket: the thing worth stopping here is a
scripted burst against ``/auth/login``, and a fixed window stops that with one
integer per client and no background sweeper thread. The known weakness of a
fixed window -- up to 2x the budget across a window boundary -- is irrelevant at
these limits.

State is per-process and in memory. With several workers the effective limit is
``workers x budget``, which is stated plainly here rather than hidden: for the
threat this addresses (credential stuffing, accidental client loops) a limit
that is 4x looser than advertised still works, and an in-memory counter cannot
fail the request path the way a Redis dependency can. ``REDIS_URL`` is already
configured for Celery, so moving to a shared counter later is a small change --
see ``_Window`` for the seam.

Deliberately *not* covered: the Meta and Vapi webhooks are exempted from the
tight auth budget because a real provider can legitimately burst deliveries, and
throttling a provider webhook loses site reports. They are still subject to the
default budget. This limits, but does not close, the unauthenticated-webhook
findings in docs/PHASE9-10-AUDIT.md -- only setting the webhook secrets does
that.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.hardening import hardening
from app.core.logging import get_logger

logger = get_logger(__name__)

# Bound the table so a spray of unique client IPs cannot grow it without limit;
# an attacker rotating IPs would otherwise turn the limiter into a memory leak.
_MAX_TRACKED_CLIENTS = 20_000


class _Window:
    """Per-client fixed-window counters, guarded by a lock.

    Replacing this class with a Redis-backed implementation is all that is
    needed to make the limit shared across workers; the middleware below only
    calls :meth:`hit`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (window_started_at, count). Ordered so the oldest entry is
        # cheapest to evict.
        self._counters: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        """Record a request. Returns ``(allowed, remaining, retry_after)``."""
        now = time.monotonic()
        with self._lock:
            started_at, count = self._counters.get(key, (now, 0))

            # Window elapsed: start a fresh one.
            if now - started_at >= window_seconds:
                started_at, count = now, 0

            count += 1
            self._counters[key] = (started_at, count)
            self._counters.move_to_end(key)

            while len(self._counters) > _MAX_TRACKED_CLIENTS:
                self._counters.popitem(last=False)

        allowed = count <= limit
        remaining = max(0, limit - count)
        retry_after = max(1, int(window_seconds - (now - started_at)))
        return allowed, remaining, retry_after

    def reset(self) -> None:
        """Drop all counters. Used by tests so one case cannot starve the next."""
        with self._lock:
            self._counters.clear()


_windows = _Window()


def reset_rate_limit_state() -> None:
    """Clear limiter state. Exposed for tests."""
    _windows.reset()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject clients that exceed their request budget with a 429."""

    def _client_key(self, request: Request) -> str:
        if hardening.TRUST_PROXY_HEADERS:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                # Left-most entry is the original client.
                return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "unknown"

    def _budget_for(self, path: str) -> tuple[int, int] | None:
        """Return ``(limit, window)``, or ``None`` when the path is exempt."""
        for exempt in hardening.RATE_LIMIT_EXEMPT_PATHS:
            if path.endswith(exempt):
                return None
        for auth_path in hardening.RATE_LIMIT_AUTH_PATHS:
            if auth_path in path:
                return (
                    hardening.RATE_LIMIT_AUTH_REQUESTS,
                    hardening.RATE_LIMIT_AUTH_WINDOW_SECONDS,
                )
        return hardening.RATE_LIMIT_REQUESTS, hardening.RATE_LIMIT_WINDOW_SECONDS

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not hardening.RATE_LIMIT_ENABLED:
            return await call_next(request)

        budget = self._budget_for(request.url.path)
        if budget is None:
            return await call_next(request)

        limit, window_seconds = budget
        # The window is keyed on path class as well as client, so exhausting the
        # login budget does not also lock the caller out of the whole API.
        is_auth = limit == hardening.RATE_LIMIT_AUTH_REQUESTS
        key = f"{self._client_key(request)}:{'auth' if is_auth else 'default'}"

        allowed, remaining, retry_after = _windows.hit(key, limit, window_seconds)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "limit": limit,
                    "window_seconds": window_seconds,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": (
                            "Too many requests. Retry in "
                            f"{retry_after} second(s)."
                        ),
                        "details": {"retry_after_seconds": retry_after},
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
