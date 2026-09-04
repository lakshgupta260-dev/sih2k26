"""Phase 11 hardening settings.

These live in their own settings object rather than in ``app.core.config`` on
purpose. Phase 9/10 added the Meta and Vapi keys to ``Settings``, and Phase 11
is under instruction to leave every Phase 9/10 file untouched -- so the
hardening knobs are declared here instead. The mechanism is the same
(``BaseSettings`` reading the environment and ``.env``), so operators configure
these exactly like any other setting; nothing about the deployment contract
changes because of where the class happens to live.

Every limit here is deliberately generous. The point of these middlewares is to
stop abuse and accidents -- a scripted credential-stuffing run, a 2 GB upload
that fills the disk -- not to throttle ordinary use. A legitimate site
supervisor filing reports all day should never notice them.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HardeningSettings(BaseSettings):
    """Rate limiting, body caps and header policy."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Read so rate limiting can default off under test. Mirrors the value in
    # ``app.core.config.Settings``; kept as a plain string here to avoid
    # importing that module and coupling the two settings objects.
    ENVIRONMENT: str = "local"

    # ------------------------------------------------------------ rate limiting
    RATE_LIMIT_ENABLED: bool = True

    # Sustained request budget per client per window, for ordinary traffic.
    RATE_LIMIT_REQUESTS: int = 300
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Authentication endpoints get a much tighter budget: these are the ones
    # worth brute-forcing, and no human logs in thirty times a minute.
    RATE_LIMIT_AUTH_REQUESTS: int = 10
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 60

    # Path prefixes (relative to the API root) treated as authentication.
    RATE_LIMIT_AUTH_PATHS: tuple[str, ...] = (
        "/auth/login",
        "/auth/register",
        "/auth/refresh",
        "/auth/password",
    )

    # Never rate limit liveness/readiness -- an orchestrator polls these hard
    # and throttling them turns a busy minute into a restart loop.
    RATE_LIMIT_EXEMPT_PATHS: tuple[str, ...] = ("/health", "/health/ready")

    # Trust a proxy's client-IP header only when the deployment actually runs
    # behind one. Left off, a client can forge X-Forwarded-For and sidestep
    # the limiter entirely by rotating the header.
    TRUST_PROXY_HEADERS: bool = False

    # ------------------------------------------------------------- body limits
    # Hard ceiling on any request body. The upload endpoints enforce their own
    # smaller, type-aware caps (Phase 3/4); this is the backstop that keeps an
    # unbounded stream from reaching them at all.
    MAX_REQUEST_BODY_BYTES: int = 64 * 1024 * 1024  # 64 MiB

    # --------------------------------------------------------- security headers
    SECURITY_HEADERS_ENABLED: bool = True
    # HSTS is only meaningful over TLS and actively unhelpful in local dev,
    # so it is opt-in per environment.
    HSTS_ENABLED: bool = False
    HSTS_MAX_AGE_SECONDS: int = 31_536_000  # one year

    # ----------------------------------------------------------- log redaction
    LOG_REDACTION_ENABLED: bool = True

    @model_validator(mode="after")
    def _disable_rate_limiting_under_test(self) -> "HardeningSettings":
        """Turn rate limiting off in the test environment.

        A test suite is indistinguishable from an attacker to a rate limiter:
        every request arrives from the same client with no pause, and the
        suite logs in hundreds of times. Leaving the limiter on made 30+
        unrelated tests fail with 429 where they asserted 401 -- the limiter
        was working exactly as designed and was still wrong to be there.

        Tests that exercise the limiter itself re-enable it explicitly (see
        ``tests/test_hardening.py``), so the behaviour is still covered. An
        explicit ``RATE_LIMIT_ENABLED=true`` in the environment still wins,
        which is what CI uses to prove the limiter works end to end.
        """
        if self.ENVIRONMENT == "test" and "RATE_LIMIT_ENABLED" not in _env_keys():
            self.RATE_LIMIT_ENABLED = False
        return self


def _env_keys() -> frozenset[str]:
    """Environment variable names, upper-cased.

    Used to tell "left at the default" apart from "explicitly set to true",
    so an operator (or CI) can force the limiter on even under test.
    """
    import os

    return frozenset(key.upper() for key in os.environ)


@lru_cache
def get_hardening_settings() -> HardeningSettings:
    return HardeningSettings()


hardening = get_hardening_settings()
