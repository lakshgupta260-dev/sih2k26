"""Phase 11 hardening: rate limits, body caps, headers, log redaction.

Each test states the behaviour it protects rather than restating the
implementation, so a rewrite of the middleware internals does not invalidate
the suite.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.hardening import hardening
from app.core.log_redaction import RedactingFilter, install_log_redaction
from app.core.rate_limit import reset_rate_limit_state


@pytest.fixture(autouse=True)
def _clean_limiter():
    """Every test starts with an empty limiter.

    Without this, the request budget leaks between tests and whichever test
    happens to run later fails for reasons that have nothing to do with it.
    """
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


@pytest.fixture
def limiter_on(monkeypatch):
    """Re-enable rate limiting for tests that are about the limiter.

    It is off by default under ENVIRONMENT=test -- see
    ``HardeningSettings._disable_rate_limiting_under_test`` for why -- so the
    tests that actually exercise it have to ask for it back.
    """
    monkeypatch.setattr(hardening, "RATE_LIMIT_ENABLED", True)
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


# --------------------------------------------------------------- rate limiting


def test_ordinary_traffic_is_not_rate_limited(client: TestClient, limiter_on) -> None:
    """The default budget must not interfere with normal use."""
    for _ in range(30):
        response = client.get("/api/v1/health")
        assert response.status_code == 200


def test_login_attempts_are_throttled_after_the_auth_budget(
    client: TestClient, monkeypatch, limiter_on
) -> None:
    """Credential stuffing gets a 429, not unlimited guesses.

    The auth budget is deliberately far tighter than the default one, because
    this is the endpoint worth brute-forcing.
    """
    monkeypatch.setattr(hardening, "RATE_LIMIT_AUTH_REQUESTS", 3)
    reset_rate_limit_state()

    statuses = [
        client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong-password"},
        ).status_code
        for _ in range(6)
    ]

    # The first three are allowed through to fail authentication normally;
    # everything after that is refused by the limiter.
    assert 429 in statuses, statuses
    assert statuses.count(429) == 3, statuses


def test_a_throttled_response_tells_the_client_when_to_retry(
    client: TestClient, monkeypatch, limiter_on
) -> None:
    monkeypatch.setattr(hardening, "RATE_LIMIT_AUTH_REQUESTS", 1)
    reset_rate_limit_state()

    client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "wrong"},
    )
    throttled = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "wrong"},
    )

    assert throttled.status_code == 429
    assert throttled.headers["Retry-After"].isdigit()
    assert throttled.json()["error"]["code"] == "RATE_LIMITED"


def test_exhausting_the_login_budget_does_not_lock_the_whole_api(
    client: TestClient, monkeypatch, limiter_on
) -> None:
    """Auth and default budgets are tracked separately.

    If they shared a counter, a few bad login attempts would take the caller's
    entire API access down with them.
    """
    monkeypatch.setattr(hardening, "RATE_LIMIT_AUTH_REQUESTS", 1)
    reset_rate_limit_state()

    for _ in range(4):
        client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong"},
        )

    assert client.get("/api/v1/health").status_code == 200


def test_health_checks_are_never_throttled(
    client: TestClient, monkeypatch, limiter_on
) -> None:
    """An orchestrator polls health hard; throttling it causes restart loops."""
    monkeypatch.setattr(hardening, "RATE_LIMIT_REQUESTS", 2)
    reset_rate_limit_state()

    statuses = [client.get("/api/v1/health").status_code for _ in range(8)]
    assert statuses == [200] * 8


def test_forged_proxy_header_cannot_be_used_to_evade_the_limit(
    client: TestClient, monkeypatch, limiter_on
) -> None:
    """With proxy trust off, rotating X-Forwarded-For must not reset the budget.

    This is the failure mode of trusting the header unconditionally: an
    attacker simply sends a new value on every request and is never limited.
    """
    monkeypatch.setattr(hardening, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(hardening, "RATE_LIMIT_AUTH_REQUESTS", 2)
    reset_rate_limit_state()

    statuses = [
        client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        ).status_code
        for i in range(6)
    ]
    assert 429 in statuses, statuses


def test_rate_limiting_can_be_switched_off(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(hardening, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(hardening, "RATE_LIMIT_AUTH_REQUESTS", 1)
    reset_rate_limit_state()

    statuses = [
        client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong"},
        ).status_code
        for _ in range(5)
    ]
    assert 429 not in statuses


# ------------------------------------------------------------ security headers


def test_responses_carry_the_hardening_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_error_responses_also_carry_the_headers(client: TestClient) -> None:
    """Headers must be present on failures too, not just the happy path."""
    response = client.get("/api/v1/projects/not-a-uuid")
    assert response.status_code >= 400
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_is_absent_unless_explicitly_enabled(client: TestClient) -> None:
    """HSTS over plain HTTP in dev would pin a broken scheme in the browser."""
    assert "Strict-Transport-Security" not in client.get("/api/v1/health").headers


def test_hsts_is_sent_when_enabled(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(hardening, "HSTS_ENABLED", True)
    header = client.get("/api/v1/health").headers.get("Strict-Transport-Security")
    assert header is not None and "max-age=" in header


# ------------------------------------------------------------------ body limit


def test_oversized_body_is_refused_with_413(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(hardening, "MAX_REQUEST_BODY_BYTES", 1024)

    response = client.post(
        "/api/v1/auth/login",
        content=b"x" * 4096,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_body_within_the_limit_is_routed_normally(
    client: TestClient, monkeypatch
) -> None:
    """The cap must not break ordinary requests."""
    monkeypatch.setattr(hardening, "MAX_REQUEST_BODY_BYTES", 1024 * 1024)
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "wrong-password"},
    )
    # Reaches the route and fails authentication, rather than being rejected
    # by the size middleware.
    assert response.status_code in (400, 401, 422)


def test_malformed_content_length_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        content=b"{}",
        headers={"Content-Length": "not-a-number", "Content-Type": "application/json"},
    )
    assert response.status_code in (400, 413, 422)


# --------------------------------------------------------------- log redaction


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.WARNING, pathname=__file__,
        lineno=1, msg=message, args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_a_configured_secret_is_masked_in_log_output(monkeypatch) -> None:
    """The exact Phase 9/10 leak: a log line containing the verify token.

    See docs/PHASE9-10-AUDIT.md finding 3 -- meta.py logs
    ``expected: <META_VERIFY_TOKEN>`` on every verification attempt.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "META_VERIFY_TOKEN", "super-secret-verify-token", raising=False)

    redacting = RedactingFilter(redact_phones=False)
    record = _record("Received token: attacker-guess, expected: super-secret-verify-token")
    redacting.filter(record)

    assert "super-secret-verify-token" not in record.getMessage()
    assert "REDACTED" in record.getMessage()
    # The non-secret half of the line survives, so the log stays useful.
    assert "attacker-guess" in record.getMessage()


def test_phone_numbers_are_partially_masked() -> None:
    """Finding 4: webhook bodies carry sender phone numbers into the logs."""
    redacting = RedactingFilter(redact_phones=True)
    record = _record("Incoming Meta webhook: {'wa_id': '919876543210'}")
    redacting.filter(record)

    message = record.getMessage()
    assert "919876543210" not in message
    # Last two digits are kept so an operator can still correlate a report.
    assert message.rstrip("'}").endswith("10")


def test_bearer_tokens_are_masked() -> None:
    redacting = RedactingFilter(redact_phones=False)
    record = _record("headers: Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop")
    redacting.filter(record)
    assert "eyJhbGciOiJIUzI1NiJ9" not in record.getMessage()


def test_structured_extras_are_scrubbed_too(monkeypatch) -> None:
    """A secret passed via extra= must not slip past the message scrub."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "VAPI_SECRET", "vapi-secret-value-1234", raising=False)

    redacting = RedactingFilter(redact_phones=False)
    record = _record("tool call", supplied_secret="vapi-secret-value-1234")
    redacting.filter(record)

    assert record.supplied_secret == "***REDACTED***"


def test_correlation_ids_and_hashes_survive_redaction() -> None:
    """Regression: the phone pattern used to eat request ids and hashes.

    Observed live before this was fixed -- a 16-char hex request id came out as
    ``e********32b43af``, which destroys the ability to trace one request across
    log lines. Correlation ids, UUIDs and SHA-256 digests all contain long digit
    runs; none of them are phone numbers.
    """
    redacting = RedactingFilter(redact_phones=True)
    samples = [
        "e52f3190923a427c",                                   # request id
        "9c1307387a70",                                       # migration revision
        "a8207366-29ad-479e-a8ec-656ad3accc64",               # uuid
        "d2c17993c6d54e90a258cea04c33516d9c1307387a70aabb",   # digest
    ]
    for sample in samples:
        record = _record(f"identifier={sample}")
        redacting.filter(record)
        assert sample in record.getMessage(), f"mangled {sample}"


def test_request_id_attribute_is_never_scrubbed() -> None:
    redacting = RedactingFilter(redact_phones=True)
    record = _record("request", request_id="e52f3190923a427c")
    redacting.filter(record)
    assert record.request_id == "e52f3190923a427c"


def test_a_real_phone_number_is_still_masked_after_the_boundary_fix() -> None:
    """The boundary fix must not stop the filter doing its actual job."""
    redacting = RedactingFilter(redact_phones=True)
    for text in ("from: +919876543210", "wa_id '919876543210'", "call 919876543210."):
        record = _record(text)
        redacting.filter(record)
        assert "919876543210" not in record.getMessage(), text


def test_ordinary_log_lines_are_left_alone() -> None:
    """Redaction must not mangle unrelated logging."""
    redacting = RedactingFilter(redact_phones=False)
    record = _record("schedule_parsed rows=42 skipped=0")
    redacting.filter(record)
    assert record.getMessage() == "schedule_parsed rows=42 skipped=0"


def test_short_secrets_are_not_masked(monkeypatch) -> None:
    """Masking a tiny value would redact unrelated text across the log file."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "META_VERIFY_TOKEN", "abc", raising=False)
    redacting = RedactingFilter(redact_phones=False)
    record = _record("the abc of it")
    redacting.filter(record)
    assert record.getMessage() == "the abc of it"


def test_installing_redaction_twice_does_not_stack_filters() -> None:
    """Startup can run more than once in tests; filters must not accumulate."""
    root = logging.getLogger()
    handler = logging.StreamHandler()
    root.addHandler(handler)
    try:
        install_log_redaction()
        install_log_redaction()
        count = sum(isinstance(f, RedactingFilter) for f in handler.filters)
        assert count == 1
    finally:
        root.removeHandler(handler)
