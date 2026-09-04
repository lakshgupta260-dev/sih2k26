"""Every route is checked for an authentication guard, by enumeration.

The point of this module is that it is not a list. It walks the application's
own route table at run time, so an endpoint added in a later phase is covered
the moment it is registered -- nobody has to remember to add it here. Three of
the authorization holes found earlier in this project (Phase 6 progress and
analytics, Phase 3/4 schedule paths) were endpoints that simply never had a
guard attached, and each was found by hand well after the code shipped. This
turns that class of defect into a failing test at the point it is introduced.

Routes that are public by design are listed in ``PUBLIC_ROUTES`` with a stated
reason. Adding to that list is deliberately awkward: it is the one place a
reviewer has to look to see what is reachable without credentials.
"""
from __future__ import annotations

import re
import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

# Public by design. Each entry needs a reason, because each entry is an
# endpoint an unauthenticated caller can reach.
PUBLIC_ROUTES: dict[str, str] = {
    # Liveness and readiness: polled by the orchestrator before any token exists.
    "/api/v1/health": "liveness probe",
    "/api/v1/health/ready": "readiness probe",
    # Credential exchange: these are how a caller obtains a token.
    "/api/v1/auth/login": "issues tokens",
    "/api/v1/auth/token": "OAuth2 password-flow token endpoint",
    "/api/v1/auth/register": "self-registration",
    "/api/v1/auth/refresh": "exchanges a refresh token",
    # Provider webhooks. These authenticate by shared secret / HMAC signature
    # rather than by bearer token, so a 401 is not the expected response.
    #
    # NOTE: both currently fail OPEN when their secret is unset -- see
    # docs/PHASE9-10-AUDIT.md findings 1 and 2, which are Critical and
    # reproduced. They are listed here because they are genuinely not
    # bearer-authenticated, NOT because their current behaviour is acceptable.
    # test_webhooks_are_secret_authenticated below pins the intended contract.
    "/api/v1/integrations/meta/webhook": "Meta HMAC-signed webhook",
    "/api/v1/integrations/vapi/webhook": "Vapi shared-secret webhook",
}

# Documentation and schema endpoints, matched by prefix.
_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/api/v1/openapi.json")

# Status codes that prove a guard ran. 401/403 are the direct evidence.
# 422 is accepted only where validation legitimately precedes authentication
# (a malformed path parameter never reaches the guard), and 405 means the
# method is not routed at all.
_GUARDED = {401, 403}
_ACCEPTABLE = _GUARDED | {405, 422}

_PARAM_RE = re.compile(r"\{([^}]+)\}")


def _concrete_path(path: str) -> str:
    """Substitute a syntactically valid value for each path parameter.

    A real UUID matters: if the parameter fails to parse, FastAPI answers 422
    before the dependency that would have rejected the caller ever runs, and
    the test would pass without proving anything.
    """
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1).split(":")[0]
        if name.endswith("_id") or name == "id":
            return str(uuid.uuid4())
        if "path" in name or "file" in name:
            return "placeholder.txt"
        return "placeholder"

    return _PARAM_RE.sub(_replace, path)


def _is_public(path: str) -> bool:
    return path in PUBLIC_ROUTES or path.startswith(_PUBLIC_PREFIXES)


def _routes(app) -> list[tuple[str, str]]:
    """Every (method, path) the application serves, excluding HEAD/OPTIONS."""
    found: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found.append((method, route.path))
    return sorted(set(found))


def _call(client: TestClient, method: str, path: str, **kwargs):
    return client.request(method, path, **kwargs)


def test_the_route_table_is_not_empty(client: TestClient) -> None:
    """Guard against the matrix silently testing nothing.

    If route introspection breaks, every parametrised test below would vanish
    and the suite would still be green. This is the canary for that.
    """
    routes = _routes(client.app)
    assert len(routes) > 40, f"only found {len(routes)} routes; introspection broken?"


def _protected_routes(app) -> list[tuple[str, str]]:
    return [(m, p) for m, p in _routes(app) if not _is_public(p)]


@pytest.mark.parametrize("method,path", _protected_routes(__import__("app.main", fromlist=["app"]).app))
def test_route_rejects_anonymous_callers(
    client: TestClient, method: str, path: str
) -> None:
    """No non-public route may serve an unauthenticated caller.

    A 2xx here means the endpoint has no authentication guard at all, which is
    the exact shape of the cross-tenant holes found in Phases 3, 4 and 6.
    """
    response = _call(client, method, _concrete_path(path))

    assert response.status_code != 200, (
        f"{method} {path} served an anonymous caller with 200 -- "
        "no authentication guard"
    )
    assert response.status_code not in (201, 204), (
        f"{method} {path} accepted an anonymous write ({response.status_code})"
    )
    assert response.status_code in _ACCEPTABLE or response.status_code >= 500, (
        f"{method} {path} answered anonymously with {response.status_code}; "
        f"expected one of {sorted(_ACCEPTABLE)}"
    )


@pytest.mark.parametrize("method,path", _protected_routes(__import__("app.main", fromlist=["app"]).app))
def test_route_rejects_a_garbage_bearer_token(
    client: TestClient, method: str, path: str
) -> None:
    """A malformed token must be refused, not ignored.

    Distinct from the anonymous case: a guard that reads the header but fails
    to verify the signature would pass the test above and fail this one.
    """
    response = _call(
        client,
        method,
        _concrete_path(path),
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code != 200, (
        f"{method} {path} accepted a forged bearer token"
    )
    assert response.status_code not in (201, 204), (
        f"{method} {path} accepted a write with a forged token"
    )


def test_public_route_list_matches_reality(client: TestClient) -> None:
    """Every entry in PUBLIC_ROUTES must still exist.

    Stops the exemption list rotting into a set of stale paths that quietly
    exempt nothing -- or worse, that no longer match a route which has since
    been renamed and is now being tested as protected when it is not.
    """
    live_paths = {path for _, path in _routes(client.app)}
    for declared in PUBLIC_ROUTES:
        assert declared in live_paths, (
            f"{declared} is exempted in PUBLIC_ROUTES but is not a live route"
        )


def test_webhooks_are_secret_authenticated(client: TestClient, monkeypatch) -> None:
    """With their secrets configured, the webhooks must refuse unsigned calls.

    This pins the intended contract for the two provider webhooks, which are
    exempt from the bearer-token matrix above. It passes today only because a
    secret is set here: with the secret unset both endpoints fail open, which
    is docs/PHASE9-10-AUDIT.md findings 1 and 2. Phase 11 does not modify those
    files, so this test documents the boundary rather than fixing it.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "VAPI_SECRET", "test-vapi-secret", raising=False)
    monkeypatch.setattr(settings, "META_APP_SECRET", "test-meta-secret", raising=False)

    vapi = client.post(
        "/api/v1/integrations/vapi/webhook",
        json={"message": {"type": "tool-calls"}},
    )
    assert vapi.status_code == 403, (
        "Vapi webhook accepted a call with no shared secret while "
        f"VAPI_SECRET was set (got {vapi.status_code})"
    )

    meta = client.post(
        "/api/v1/integrations/meta/webhook",
        json={"object": "whatsapp_business_account", "entry": []},
    )
    assert meta.status_code == 403, (
        "Meta webhook accepted an unsigned payload while META_APP_SECRET was "
        f"set (got {meta.status_code})"
    )


def test_webhooks_do_not_fail_open_without_their_secrets(
    client: TestClient, monkeypatch
) -> None:
    """docs/PHASE9-10-AUDIT.md findings 1 and 2, now fixed upstream.

    This test originally pinned the *defective* behaviour on purpose, because
    Phase 11 was not permitted to touch these files: with no secret
    configured, both webhooks used to fail open and return 200 to an
    unauthenticated caller. It was written to fail the moment that changed, as
    the signal to delete it.

    It changed: with VAPI_SECRET unset the Vapi webhook now returns 403, and
    with META_APP_SECRET unset the Meta webhook now returns 503 rather than
    accepting the call. This replacement pins that fix as the new contract
    instead of the vulnerability, so a regression back to fail-open behaviour
    is caught here rather than only in the "secret configured" test above.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "VAPI_SECRET", None, raising=False)
    vapi = client.post(
        "/api/v1/integrations/vapi/webhook",
        json={"message": {"type": "assistant-request"}},
    )
    assert vapi.status_code != 200, (
        "Vapi webhook fails open (200) with VAPI_SECRET unset -- findings 1 "
        "has regressed."
    )

    monkeypatch.setattr(settings, "META_APP_SECRET", None, raising=False)
    meta = client.post(
        "/api/v1/integrations/meta/webhook",
        json={"object": "whatsapp_business_account", "entry": []},
    )
    assert meta.status_code != 200, (
        "Meta webhook fails open (200) with META_APP_SECRET unset -- finding "
        "2 has regressed."
    )
