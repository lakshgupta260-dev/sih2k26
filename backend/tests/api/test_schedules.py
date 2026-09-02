import pytest
import io
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.constants import ProjectStatus

@pytest.fixture
def test_project(client, db, manager_user, auth_headers):
    # Setup a project for our manager
    h = auth_headers(manager_user)
    r = client.post("/api/v1/projects", json={
        "code": "TEST-SCHED",
        "name": "Test Schedule Project"
    }, headers=h)
    assert r.status_code == 201
    return r.json()["id"], h

def make_csv(lines):
    return io.BytesIO("\n".join(lines).encode("utf-8"))

def upload_schedule(client, project_id, headers, csv_content, mapping=None):
    if mapping is None:
        mapping = '{"activity_code": "ID", "name": "Name", "wbs_path": "WBS", "level": "Lvl", "discipline": "Disc", "predecessors": "Pred"}'
    
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {
        "name": "Test Schedule",
        "mapping": mapping
    }
    return client.post(f"/api/v1/projects/{project_id}/schedules", files=files, data=data, headers=headers)

def test_missing_required_column_fails(client, test_project):
    pid, headers = test_project
    csv = make_csv(["ID,Other", "A1,Value"])
    mapping = '{"activity_code": "ID", "name": "Name"}'
    r = upload_schedule(client, pid, headers, csv, mapping)
    assert r.status_code == 400
    assert "Required column 'Name' not found" in r.text

def test_wbs_paths_are_not_type_coerced(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,WBS",
        "A1,Root,1",
        "A2,Child,1.10"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201
    sid = r.json()["id"]
    
    r = client.get(f"/api/v1/projects/{pid}/schedules/{sid}", headers=headers)
    assert r.status_code == 200
    # check activities
    r = client.get(f"/api/v1/schedules/{sid}/activities", headers=headers)
    assert r.status_code == 200
    acts = {a["activity_code"]: a["wbs_path"] for a in r.json()["items"]}
    assert acts["A1"] == "1"
    assert acts["A2"] == "1.10" # D1 fixed!

def test_discipline_normalised_to_enum(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,Disc",
        "A1,Task1,civil works",
        "A2,Task2,JUNK"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201
    sid = r.json()["id"]
    
    r = client.get(f"/api/v1/schedules/{sid}/activities", headers=headers)
    acts = {a["activity_code"]: a["discipline"] for a in r.json()["items"]}
    assert acts["A1"] == "CIVIL"
    assert acts["A2"] == "OTHER"

def test_level_out_of_range_rejected(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,Lvl",
        "A1,Task1,7"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 400
    assert "Level must be between 1 and 6" in r.text

def test_dependency_cycle_rejected(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,Pred",
        "A1,Task1,A2",
        "A2,Task2,A1"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 400
    assert "Circular dependency" in r.text

def test_self_dependency_rejected(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,Pred",
        "A1,Task1,A1"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 400
    assert "lists itself as a predecessor" in r.text

def test_duplicate_activity_code_rejected(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name",
        "A1,Task1",
        "A1,Task2"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 400
    assert "Duplicate activity code 'A1'" in r.text

def test_dependency_type_and_lag_parsed(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,Pred",
        "A1,Task1,",
        "A2,Task2,A1FS+3"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201
    sid = r.json()["id"]
    
    # get A2 details
    r = client.get(f"/api/v1/schedules/{sid}/activities", headers=headers)
    a2_id = next(a["id"] for a in r.json()["items"] if a["activity_code"] == "A2")
    r2 = client.get(f"/api/v1/schedules/{sid}/activities/{a2_id}", headers=headers)
    assert r2.status_code == 200
    preds = r2.json()["predecessors"]
    assert len(preds) == 1
    assert preds[0]["dependency_type"] == "FS"
    assert preds[0]["lag"] == 3.0

def test_supervisor_cannot_upload_schedule(client, test_project, supervisor_user, auth_headers):
    pid, _ = test_project
    _, h = test_project
    r = client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(supervisor_user.id), "role": "SITE_SUPERVISOR"}, headers=h)
    assert r.status_code == 201

    sh = auth_headers(supervisor_user)
    csv = make_csv(["ID,Name", "A1,Task1"])
    r = upload_schedule(client, pid, sh, csv)
    assert r.status_code == 403

def test_activity_tree_endpoint(client, test_project):
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,WBS",
        "A1,Root,1",
        "A2,Child1,1.1",
        "A3,Child2,1.2"
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201
    sid = r.json()["id"]
    
    r = client.get(f"/api/v1/schedules/{sid}/activities/tree", headers=headers)
    assert r.status_code == 200
    tree = r.json()
    assert len(tree) == 1
    assert tree[0]["activity_code"] == "A1"
    assert len(tree[0]["children"]) == 2
