"""System-role authorization (RBAC)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.constants import UserRole

USERS = "/api/v1/users"


def test_role_set_is_exactly_three() -> None:
    assert {r.value for r in UserRole} == {
        "ADMIN",
        "PROJECT_MANAGER",
        "SITE_SUPERVISOR",
    }


def test_admin_can_list_users(client: TestClient, admin_user, auth_headers) -> None:
    response = client.get(USERS, headers=auth_headers(admin_user))
    assert response.status_code == 200
    body = response.json()
    assert {"items", "total", "skip", "limit"} <= set(body)


@pytest.mark.parametrize("role", [UserRole.PROJECT_MANAGER, UserRole.SITE_SUPERVISOR])
def test_non_admin_cannot_list_users(
    client: TestClient, make_user, auth_headers, role: UserRole
) -> None:
    user = make_user(role)
    response = client.get(USERS, headers=auth_headers(user))
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "PERMISSION_DENIED"
    assert error["details"]["your_role"] == role.value


def test_unauthenticated_list_users_is_401_not_403(client: TestClient) -> None:
    """Missing credentials must read as 401; wrong role as 403."""
    assert client.get(USERS).status_code == 401


def test_admin_can_create_user_with_role(
    client: TestClient, admin_user, auth_headers
) -> None:
    response = client.post(
        USERS,
        json={
            "email": "made.by.admin@example.com",
            "password": "AdminMade123",
            "full_name": "Made By Admin",
            "role": "PROJECT_MANAGER",
        },
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "PROJECT_MANAGER"


def test_supervisor_cannot_create_users(
    client: TestClient, supervisor_user, auth_headers
) -> None:
    response = client.post(
        USERS,
        json={
            "email": "nope@example.com",
            "password": "Nope12345",
            "full_name": "Nope",
            "role": "ADMIN",
        },
        headers=auth_headers(supervisor_user),
    )
    assert response.status_code == 403


def test_user_can_read_own_record(
    client: TestClient, supervisor_user, auth_headers
) -> None:
    response = client.get(
        f"{USERS}/{supervisor_user.id}", headers=auth_headers(supervisor_user)
    )
    assert response.status_code == 200


def test_user_cannot_read_another_users_record(
    client: TestClient, make_user, auth_headers
) -> None:
    me = make_user()
    other = make_user()
    response = client.get(f"{USERS}/{other.id}", headers=auth_headers(me))
    assert response.status_code == 403


def test_admin_can_read_any_user(
    client: TestClient, admin_user, make_user, auth_headers
) -> None:
    other = make_user()
    response = client.get(f"{USERS}/{other.id}", headers=auth_headers(admin_user))
    assert response.status_code == 200


def test_user_cannot_change_own_role_via_profile_update(
    client: TestClient, supervisor_user, auth_headers
) -> None:
    """UserUpdate has no role field, so the attempt must be a no-op."""
    response = client.patch(
        f"{USERS}/{supervisor_user.id}",
        json={"full_name": "Renamed", "role": "ADMIN"},
        headers=auth_headers(supervisor_user),
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed"
    assert response.json()["role"] == UserRole.SITE_SUPERVISOR


def test_admin_role_change_revokes_target_sessions(
    client: TestClient, admin_user, make_user, auth_headers
) -> None:
    target = make_user()
    target_tokens = client.post(
        "/api/v1/auth/login",
        json={"email": target.email, "password": "TestPass123"},
    ).json()

    promoted = client.patch(
        f"{USERS}/{target.id}/role",
        json={"role": "PROJECT_MANAGER"},
        headers=auth_headers(admin_user),
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "PROJECT_MANAGER"

    # The old refresh token carried the old role and must no longer work.
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": target_tokens["refresh_token"]},
    ).status_code == 401


def test_admin_cannot_demote_self(
    client: TestClient, admin_user, auth_headers
) -> None:
    response = client.patch(
        f"{USERS}/{admin_user.id}/role",
        json={"role": "SITE_SUPERVISOR"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SELF_ROLE_CHANGE"


def test_last_admin_cannot_be_demoted(
    client: TestClient, admin_user, make_user, auth_headers
) -> None:
    """Two admins: the acting one may demote the other only if one remains."""
    other_admin = make_user(UserRole.ADMIN)
    headers = auth_headers(admin_user)

    first = client.patch(
        f"{USERS}/{other_admin.id}/role",
        json={"role": "SITE_SUPERVISOR"},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    # admin_user is now the only admin and cannot demote itself either
    second = client.patch(
        f"{USERS}/{admin_user.id}/role",
        json={"role": "SITE_SUPERVISOR"},
        headers=headers,
    )
    assert second.status_code == 422


def test_deactivating_a_user_revokes_sessions_and_blocks_login(
    client: TestClient, admin_user, make_user, auth_headers
) -> None:
    target = make_user()
    tokens = client.post(
        "/api/v1/auth/login",
        json={"email": target.email, "password": "TestPass123"},
    ).json()

    response = client.patch(
        f"{USERS}/{target.id}/status",
        json={"is_active": False},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": target.email, "password": "TestPass123"},
    ).status_code == 401


def test_admin_cannot_deactivate_self(
    client: TestClient, admin_user, auth_headers
) -> None:
    response = client.patch(
        f"{USERS}/{admin_user.id}/status",
        json={"is_active": False},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SELF_DEACTIVATE"
