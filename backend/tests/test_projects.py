"""Project CRUD, membership management and project-level authorization."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.constants import UserRole

PROJECTS = "/api/v1/projects"


def _payload(code: str = "PROJ-TEST-01", **over) -> dict:
    body = {
        "code": code,
        "name": "Test Trunk Pipeline",
        "description": "Synthetic project for tests",
        "client_name": "Test Client",
        "location": "Assam",
        "planned_start": "2026-01-05",
        "planned_finish": "2026-12-20",
    }
    body.update(over)
    return body


def _create(client: TestClient, headers: dict, **over) -> dict:
    response = client.post(PROJECTS, json=_payload(**over), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# -------------------------------------------------------------------- create
@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.PROJECT_MANAGER])
def test_admin_and_manager_can_create(
    client: TestClient, make_user, auth_headers, role: UserRole
) -> None:
    actor = make_user(role)
    body = _create(client, auth_headers(actor), code=f"P-{role.value[:4]}-1")
    assert body["created_by_id"] == str(actor.id)


def test_supervisor_cannot_create_project(
    client: TestClient, supervisor_user, auth_headers
) -> None:
    response = client.post(
        PROJECTS, json=_payload(), headers=auth_headers(supervisor_user)
    )
    assert response.status_code == 403


def test_creating_a_project_enrols_creator_as_manager(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers)
    fetched = client.get(f"{PROJECTS}/{project['id']}", headers=headers).json()
    assert fetched["my_role"] == UserRole.PROJECT_MANAGER


def test_duplicate_code_is_rejected(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    _create(client, headers, code="PROJ-DUP-1")
    again = client.post(PROJECTS, json=_payload(code="PROJ-DUP-1"), headers=headers)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "PROJECT_CODE_TAKEN"


def test_finish_before_start_is_rejected(
    client: TestClient, manager_user, auth_headers
) -> None:
    response = client.post(
        PROJECTS,
        json=_payload(planned_start="2026-06-01", planned_finish="2026-01-01"),
        headers=auth_headers(manager_user),
    )
    assert response.status_code == 422


def test_project_creation_requires_authentication(client: TestClient) -> None:
    assert client.post(PROJECTS, json=_payload()).status_code == 401


# ---------------------------------------------------------- visibility scope
def test_non_member_cannot_see_project_in_list(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    _create(client, auth_headers(manager_user), code="PROJ-HIDDEN-1")
    outsider = make_user(UserRole.PROJECT_MANAGER)
    listing = client.get(PROJECTS, headers=auth_headers(outsider)).json()
    assert listing["total"] == 0
    assert listing["items"] == []


def test_non_member_gets_404_not_403(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    """404 rather than 403: confirming a project id exists is itself a leak."""
    project = _create(client, auth_headers(manager_user), code="PROJ-SECRET-1")
    outsider = make_user(UserRole.PROJECT_MANAGER)
    response = client.get(
        f"{PROJECTS}/{project['id']}", headers=auth_headers(outsider)
    )
    assert response.status_code == 404


def test_admin_sees_every_project_without_membership(
    client: TestClient, manager_user, admin_user, auth_headers
) -> None:
    project = _create(client, auth_headers(manager_user), code="PROJ-ADMINVIEW-1")
    response = client.get(
        f"{PROJECTS}/{project['id']}", headers=auth_headers(admin_user)
    )
    assert response.status_code == 200
    assert response.json()["my_role"] == UserRole.PROJECT_MANAGER


def test_member_sees_project_with_their_own_role(
    client: TestClient, manager_user, supervisor_user, auth_headers
) -> None:
    mgr_headers = auth_headers(manager_user)
    project = _create(client, mgr_headers, code="PROJ-MEMBER-1")
    added = client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": supervisor_user.email, "role": "SITE_SUPERVISOR"},
        headers=mgr_headers,
    )
    assert added.status_code == 201, added.text

    listing = client.get(PROJECTS, headers=auth_headers(supervisor_user)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["my_role"] == UserRole.SITE_SUPERVISOR


def test_unknown_project_id_is_404(
    client: TestClient, manager_user, auth_headers
) -> None:
    response = client.get(
        f"{PROJECTS}/{uuid.uuid4()}", headers=auth_headers(manager_user)
    )
    assert response.status_code == 404


# -------------------------------------------------------------------- update
def test_project_manager_can_update(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-UPD-1")
    response = client.patch(
        f"{PROJECTS}/{project['id']}",
        json={"name": "Renamed Pipeline", "status": "ACTIVE"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed Pipeline"
    assert response.json()["status"] == "ACTIVE"


def test_site_supervisor_member_cannot_update(
    client: TestClient, manager_user, supervisor_user, auth_headers
) -> None:
    mgr = auth_headers(manager_user)
    project = _create(client, mgr, code="PROJ-UPD-2")
    client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": supervisor_user.email, "role": "SITE_SUPERVISOR"},
        headers=mgr,
    )
    response = client.patch(
        f"{PROJECTS}/{project['id']}",
        json={"name": "Hijacked"},
        headers=auth_headers(supervisor_user),
    )
    assert response.status_code == 403


def test_update_rejects_inverted_dates(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-UPD-3")
    response = client.patch(
        f"{PROJECTS}/{project['id']}",
        json={"planned_finish": "2025-01-01"},
        headers=headers,
    )
    assert response.status_code == 422


def test_soft_delete_hides_project(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-DEL-1")
    assert client.delete(f"{PROJECTS}/{project['id']}", headers=headers).status_code == 200
    assert client.get(f"{PROJECTS}/{project['id']}", headers=headers).status_code == 404
    assert client.get(PROJECTS, headers=headers).json()["total"] == 0


# ---------------------------------------------------------------- membership
def test_add_member_by_email_and_by_id(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-1")
    by_email = make_user()
    by_id = make_user()

    assert client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": by_email.email},
        headers=headers,
    ).status_code == 201
    assert client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"user_id": str(by_id.id)},
        headers=headers,
    ).status_code == 201

    members = client.get(f"{PROJECTS}/{project['id']}/members", headers=headers).json()
    assert members["total"] == 3  # creator + two added


def test_add_member_requires_exactly_one_identifier(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-2")
    target = make_user()
    both = client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": target.email, "user_id": str(target.id)},
        headers=headers,
    )
    neither = client.post(
        f"{PROJECTS}/{project['id']}/members", json={}, headers=headers
    )
    assert both.status_code == 422
    assert neither.status_code == 422


def test_duplicate_membership_is_rejected(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-3")
    target = make_user()
    client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": target.email},
        headers=headers,
    )
    again = client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": target.email},
        headers=headers,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_MEMBER"


def test_deactivated_user_cannot_be_added(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-4")
    inactive = make_user(is_active=False)
    response = client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": inactive.email},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "USER_INACTIVE"


def test_supervisor_member_cannot_add_members(
    client: TestClient, manager_user, supervisor_user, make_user, auth_headers
) -> None:
    mgr = auth_headers(manager_user)
    project = _create(client, mgr, code="PROJ-MEM-5")
    client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": supervisor_user.email},
        headers=mgr,
    )
    outsider = make_user()
    response = client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": outsider.email},
        headers=auth_headers(supervisor_user),
    )
    assert response.status_code == 403


def test_promoting_and_removing_members(
    client: TestClient, manager_user, make_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-6")
    target = make_user()
    client.post(
        f"{PROJECTS}/{project['id']}/members",
        json={"email": target.email},
        headers=headers,
    )

    promoted = client.patch(
        f"{PROJECTS}/{project['id']}/members/{target.id}",
        json={"role": "PROJECT_MANAGER"},
        headers=headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "PROJECT_MANAGER"

    removed = client.delete(
        f"{PROJECTS}/{project['id']}/members/{target.id}", headers=headers
    )
    assert removed.status_code == 200
    assert client.get(
        f"{PROJECTS}/{project['id']}/members", headers=headers
    ).json()["total"] == 1


def test_last_project_manager_cannot_be_removed(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-7")
    response = client.delete(
        f"{PROJECTS}/{project['id']}/members/{manager_user.id}", headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LAST_PROJECT_MANAGER"


def test_last_project_manager_cannot_be_demoted(
    client: TestClient, manager_user, auth_headers
) -> None:
    headers = auth_headers(manager_user)
    project = _create(client, headers, code="PROJ-MEM-8")
    response = client.patch(
        f"{PROJECTS}/{project['id']}/members/{manager_user.id}",
        json={"role": "SITE_SUPERVISOR"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LAST_PROJECT_MANAGER"


def test_membership_is_scoped_to_one_project(
    client: TestClient, make_user, auth_headers
) -> None:
    """A member of project A must not gain any access to project B."""
    mgr_a = make_user(UserRole.PROJECT_MANAGER)
    mgr_b = make_user(UserRole.PROJECT_MANAGER)
    shared = make_user()

    project_a = _create(client, auth_headers(mgr_a), code="PROJ-ISO-A")
    project_b = _create(client, auth_headers(mgr_b), code="PROJ-ISO-B")

    client.post(
        f"{PROJECTS}/{project_a['id']}/members",
        json={"email": shared.email},
        headers=auth_headers(mgr_a),
    )

    headers = auth_headers(shared)
    assert client.get(f"{PROJECTS}/{project_a['id']}", headers=headers).status_code == 200
    assert client.get(f"{PROJECTS}/{project_b['id']}", headers=headers).status_code == 404
    assert client.get(
        f"{PROJECTS}/{project_b['id']}/members", headers=headers
    ).status_code == 404
