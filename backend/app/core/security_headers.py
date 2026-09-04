"""Response security headers and a hard request-body ceiling.

Two small middlewares that close off whole classes of problem cheaply.

The headers are chosen for an API that also serves ``/docs``. The CSP is
deliberately permissive enough for Swagger UI to work (it loads its bundle from
a CDN and uses inline styles) and is *not* a substitute for a real front-end
CSP -- the browser app that eventually consumes this API needs its own, tighter
one. Getting a policy that breaks the docs page would be worse than useless,
because the first thing anyone does is turn it off.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.hardening import hardening
from app.core.logging import get_logger

logger = get_logger(__name__)

# Swagger UI needs CDN scripts/styles and inline styles; everything else is
# locked to same-origin. frame-ancestors 'none' is the header-level equivalent
# of X-Frame-Options: DENY and covers browsers that ignore the older header.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

_STATIC_HEADERS = {
    # Stop browsers guessing a content type and executing an upload as HTML.
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Don't leak API paths (which contain project and activity ids) to
    # third-party sites via the Referer header.
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": _CSP,
    # This API has no need of camera, microphone or geolocation.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # API responses are per-user; keep them out of shared caches.
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        if not hardening.SECURITY_HEADERS_ENABLED:
            return response

        for header, value in _STATIC_HEADERS.items():
            # Never clobber a header a route set deliberately -- a file download
            # sets its own Cache-Control and Content-Disposition.
            response.headers.setdefault(header, value)

        if hardening.HSTS_ENABLED:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={hardening.HSTS_MAX_AGE_SECONDS}; includeSubDomains",
            )

        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies with 413 before they are buffered.

    The declared ``Content-Length`` is checked first, which rejects the common
    case without reading a byte. A body sent with chunked transfer encoding has
    no declared length, so those are measured as they stream and cut off once
    the ceiling is passed -- otherwise the limit would be trivially bypassed by
    omitting the header.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        limit = hardening.MAX_REQUEST_BODY_BYTES

        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    return self._too_large(request, int(declared), limit)
            except ValueError:
                # A malformed Content-Length is not something to guess about.
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "BAD_REQUEST",
                            "message": "Malformed Content-Length header.",
                            "details": {},
                        }
                    },
                )
            return await call_next(request)

        # No declared length: meter the stream.
        received = 0
        body_chunks: list[bytes] = []
        async for chunk in request.stream():
            received += len(chunk)
            if received > limit:
                return self._too_large(request, received, limit)
            body_chunks.append(chunk)

        body = b"".join(body_chunks)

        # The stream has been consumed, so hand the route a replayable copy.
        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]
        return await call_next(request)

    def _too_large(self, request: Request, size: int, limit: int) -> Response:
        logger.warning(
            "request_body_too_large",
            extra={"path": request.url.path, "bytes": size, "limit": limit},
        )
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": (
                        f"Request body exceeds the {limit} byte limit."
                    ),
                    "details": {"limit_bytes": limit},
                }
            },
        )
