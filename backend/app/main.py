"""FastAPI application factory and entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.hardening import hardening
from app.core.log_redaction import install_log_redaction
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_headers import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.db.session import check_database_connection

logger = get_logger(__name__)


def _ensure_runtime_dirs() -> None:
    for directory in (settings.UPLOAD_DIR, settings.GENERATED_REPORTS_DIR):
        Path(directory).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    A failed database check is logged loudly but does not abort startup: the
    readiness endpoint reports it, which lets an orchestrator hold traffic while
    the database finishes coming up rather than crash-looping the API.
    """
    configure_logging(settings.LOG_LEVEL, settings.LOG_JSON)
    # Must run after configure_logging, which installs the handlers this
    # attaches to. Mitigates the confirmed secret/PII log leaks documented in
    # docs/PHASE9-10-AUDIT.md findings 3 and 4.
    if hardening.LOG_REDACTION_ENABLED:
        install_log_redaction()
    _ensure_runtime_dirs()
    logger.info(
        "application_starting",
        extra={"environment": settings.ENVIRONMENT, "debug": settings.DEBUG},
    )
    if check_database_connection():
        logger.info("database_connection_ok")
    else:
        logger.warning("database_connection_failed_at_startup")
    yield
    logger.info("application_shutdown")


def create_application() -> FastAPI:
    """Build the ASGI app. Kept as a factory so tests can build isolated apps."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=(
            "Backend for SIH 2026 problem statement 26122 -- bridging planned "
            "L1-L6 project schedules with actual site progress."
        ),
        version="0.1.0",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Starlette runs middleware in reverse registration order, so the last one
    # added is the outermost. The ordering below is deliberate:
    #   CORS (outermost)  -- a rejected preflight must still carry CORS headers
    #   RateLimit         -- reject floods before any body is read
    #   BodySizeLimit     -- reject oversized bodies before routing
    #   SecurityHeaders   -- wraps the app so even error responses get headers
    #   RequestContext    -- innermost; request id is available to handlers
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_application()
