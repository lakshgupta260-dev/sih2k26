"""Authentication endpoint behaviour."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.constants import UserRole
from tests.conftest import DEFAULT_PASSWORD

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


# ------------------------------------------------------------------ register
def test_register_creates_supervisor(client: TestClient) -> None:
    response = client.post(
        REGISTER,
        json={
            "email": "New.User@Example.com",
            "password": "GoodPass123",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.user@example.com", "email must be normalised"
    assert body["role"] == UserRole.SITE_SUPERVISOR
    assert "password" not in body and "hashed_password" not in body


def test_register_rejects_duplicate_email(client: TestClient, make_user) -> None:
    existing = make_user()
    response = client.post(
        REGISTER,
        json={
            "email": existing.email.upper(),
            "password": "GoodPass123",
            "full_name": "Impostor",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_cannot_self_assign_admin(client: TestClient) -> None:
    """A role field in the payload must be ignored, not honoured."""
    response = client.post(
        REGISTER,
        json={
            "email": "sneaky@example.com",
            "password": "GoodPass123",
            "full_name": "Sneaky",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == UserRole.SITE_SUPERVISOR


@pytest.mark.parametrize(
    "password",
    ["short1", "alllettersonly", "12345678901", "x" * 80],
)
def test_register_rejects_weak_or_oversized_passwords(
    client: TestClient, password: str
) -> None:
    response = client.post(
        REGISTER,
        json={
            "email": f"weak-{len(password)}@example.com",
            "password": password,
            "full_name": "Weak",
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------- login
def test_login_returns_token_pair_and_user(client: TestClient, make_user) -> None:
    user = make_user()
    response = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert body["user"]["email"] == user.email


def test_login_wrong_password_is_401(client: TestClient, make_user) -> None:
    user = make_user()
    response = client.post(LOGIN, json={"email": user.email, "password": "WrongPass9"})
    assert response.status_code == 401


def test_login_unknown_email_gives_identical_error(
    client: TestClient, make_user
) -> None:
    """Unknown-user and wrong-password must be indistinguishable."""
    user = make_user()
    unknown = client.post(
        LOGIN, json={"email": "nobody@example.com", "password": "WrongPass9"}
    )
    wrong = client.post(LOGIN, json={"email": user.email, "password": "WrongPass9"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_login_rejects_deactivated_account(client: TestClient, make_user) -> None:
    user = make_user(is_active=False)
    response = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 401


def test_oauth2_form_login_works_for_swagger(client: TestClient, make_user) -> None:
    user = make_user()
    response = client.post(
        "/api/v1/auth/token",
        data={"username": user.email, "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


# ------------------------------------------------------------------------ me
def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_me_returns_current_user(client: TestClient, make_user, auth_headers) -> None:
    user = make_user()
    response = client.get(ME, headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


def test_me_rejects_expired_token(client: TestClient, make_user) -> None:
    user = make_user()
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "jti": "expired-token",
            "exp": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp()),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    response = client.get(ME, headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_refresh_token_is_not_accepted_as_access_token(
    client: TestClient, make_user
) -> None:
    """The type claim must stop a refresh token authenticating a request."""
    user = make_user()
    tokens = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()
    response = client.get(
        ME, headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_WRONG_TYPE"


def test_token_signed_with_wrong_key_is_rejected(
    client: TestClient, make_user
) -> None:
    user = make_user()
    forged = jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "jti": "forged",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        "an-attacker-chosen-key",
        algorithm="HS256",
    )
    response = client.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


# ------------------------------------------------------------------- refresh
def test_refresh_issues_new_pair(client: TestClient, make_user) -> None:
    user = make_user()
    first = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()
    response = client.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"], "must rotate"


def test_rotated_refresh_token_cannot_be_reused(
    client: TestClient, make_user
) -> None:
    user = make_user()
    first = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()
    client.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    replay = client.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "TOKEN_REVOKED"


def test_reuse_of_revoked_token_kills_all_sessions(
    client: TestClient, make_user
) -> None:
    """Replay implies theft, so every live session for that user is dropped."""
    user = make_user()
    session_a = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()
    session_b = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()

    client.post(REFRESH, json={"refresh_token": session_a["refresh_token"]})
    client.post(REFRESH, json={"refresh_token": session_a["refresh_token"]})

    # session B was never compromised, but must also be invalidated
    after = client.post(REFRESH, json={"refresh_token": session_b["refresh_token"]})
    assert after.status_code == 401


# -------------------------------------------------------------------- logout
def test_logout_revokes_the_supplied_session(client: TestClient, make_user) -> None:
    user = make_user()
    tokens = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    out = client.post(
        LOGOUT, json={"refresh_token": tokens["refresh_token"]}, headers=headers
    )
    assert out.status_code == 200
    assert client.post(
        REFRESH, json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 401


def test_logout_without_token_revokes_every_session(
    client: TestClient, make_user
) -> None:
    user = make_user()
    a = client.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}).json()
    b = client.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}).json()
    client.post(
        LOGOUT, json={}, headers={"Authorization": f"Bearer {a['access_token']}"}
    )
    for token in (a["refresh_token"], b["refresh_token"]):
        assert client.post(REFRESH, json={"refresh_token": token}).status_code == 401


def test_user_cannot_revoke_another_users_session(
    client: TestClient, make_user
) -> None:
    victim = make_user()
    attacker = make_user()
    victim_tokens = client.post(
        LOGIN, json={"email": victim.email, "password": DEFAULT_PASSWORD}
    ).json()
    attacker_tokens = client.post(
        LOGIN, json={"email": attacker.email, "password": DEFAULT_PASSWORD}
    ).json()

    client.post(
        LOGOUT,
        json={"refresh_token": victim_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {attacker_tokens['access_token']}"},
    )
    # The victim's session must still work.
    assert client.post(
        REFRESH, json={"refresh_token": victim_tokens["refresh_token"]}
    ).status_code == 200


# ----------------------------------------------------------- change password
def test_change_password_revokes_sessions_and_updates_credentials(
    client: TestClient, make_user
) -> None:
    user = make_user()
    tokens = client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": DEFAULT_PASSWORD, "password": "BrandNew456"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text

    assert client.post(
        REFRESH, json={"refresh_token": tokens["refresh_token"]}
    ).status_code == 401
    assert client.post(
        LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD}
    ).status_code == 401
    assert client.post(
        LOGIN, json={"email": user.email, "password": "BrandNew456"}
    ).status_code == 200


def test_change_password_requires_correct_current_password(
    client: TestClient, make_user, auth_headers
) -> None:
    user = make_user()
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "NotMyPass1", "password": "BrandNew456"},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CURRENT_PASSWORD"
