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


# ---------------------------------------------------------------------------
# Regression tests for the Phase 3 defects found by auditing this phase
# against a live API. Each was reproduced before being fixed.
# ---------------------------------------------------------------------------

def test_malformed_mapping_is_a_client_error_not_a_500(client, test_project):
    """The schedule row used to be committed before the mapping was parsed, so
    bad JSON produced an unhandled 500 and left a schedule stuck in PENDING
    that nothing would ever move on."""
    pid, headers = test_project
    for bad in ("{not json", "[]", '{"name": "Name"}'):
        r = upload_schedule(client, pid, headers,
                            make_csv(["ID,Name", "A1,Task1"]), mapping=bad)
        assert 400 <= r.status_code < 500, f"mapping {bad!r} gave {r.status_code}"

    listing = client.get(f"/api/v1/projects/{pid}/schedules?limit=100",
                         headers=headers).json()
    assert listing["total"] == 0, "a rejected upload left a schedule behind"


def test_oversized_upload_is_rejected(client, test_project, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    pid, headers = test_project
    payload = io.BytesIO(b"ID,Name\n" + b"A1,Task1\n" + b"#" + b"x" * (2 * 1024 * 1024))
    r = upload_schedule(client, pid, headers, payload)
    assert r.status_code == 422, r.text
    assert client.get(f"/api/v1/projects/{pid}/schedules",
                      headers=headers).json()["total"] == 0


def test_non_schedule_file_type_is_rejected(client, test_project):
    """A PDF is in the global upload allowlist but this endpoint cannot parse
    one; accepting it created a schedule row and then failed on read."""
    pid, headers = test_project
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    r = client.post(f"/api/v1/projects/{pid}/schedules", files=files,
                    data={"name": "S", "mapping": '{"activity_code":"ID","name":"Name"}'},
                    headers=headers)
    assert r.status_code == 422, r.text


def test_uppercase_extension_is_accepted(client, test_project):
    """SCHEDULE.CSV is what Excel on Windows produces by default."""
    pid, headers = test_project
    files = {"file": ("SCHEDULE.CSV", make_csv(["ID,Name", "A1,Task1"]), "text/csv")}
    r = client.post(f"/api/v1/projects/{pid}/schedules", files=files,
                    data={"name": "Upper",
                          "mapping": '{"activity_code":"ID","name":"Name"}'},
                    headers=headers)
    assert r.status_code == 201, r.text


def test_lag_units_are_converted_to_days(client, test_project):
    """`lag` is a float column in days. Storing "+8h" as 8 makes every
    consumer read eight hours as eight days."""
    pid, headers = test_project
    csv = make_csv([
        "ID,Name,Pred",
        "A1,First,",
        "A2,Hours,A1FS+8h",
        "A3,Weeks,A1FS+2w",
        "A4,Half,A1FS+0.5",
        "A5,Negative,A1SS-2",
    ])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    acts = client.get(f"/api/v1/schedules/{sid}/activities?limit=50",
                      headers=headers).json()["items"]
    by_code = {a["activity_code"]: a["id"] for a in acts}

    def lag_of(code):
        detail = client.get(f"/api/v1/schedules/{sid}/activities/{by_code[code]}",
                            headers=headers).json()
        return detail["predecessors"][0]

    assert lag_of("A2")["lag"] == pytest.approx(8 / 24)
    assert lag_of("A3")["lag"] == pytest.approx(14.0)
    assert lag_of("A4")["lag"] == pytest.approx(0.5), "fractional lag truncated"
    assert lag_of("A5")["lag"] == pytest.approx(-2.0)
    assert lag_of("A5")["dependency_type"] == "SS"


def test_duplicate_predecessor_references_are_collapsed(client, test_project):
    pid, headers = test_project
    csv = make_csv(["ID,Name,Pred", "A1,First,", 'A2,Second,"A1,A1FS"'])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201, r.text
    summary = r.json()["parse_summary"]
    assert summary["dependencies_created"] == 1
    assert summary["dependencies_duplicate"] == 1


def test_unresolvable_predecessors_are_counted_not_dropped_silently(
    client, test_project
):
    pid, headers = test_project
    csv = make_csv(["ID,Name,Pred", "A1,First,", "A2,Second,NOSUCH999"])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201, r.text
    summary = r.json()["parse_summary"]
    assert summary["predecessors_unresolved"] == 1
    assert summary["dependencies_created"] == 0
    assert any("NOSUCH999" in w for w in summary["warnings"])


def test_blank_rows_are_counted(client, test_project):
    pid, headers = test_project
    csv = make_csv(["ID,Name", "A1,Task1", ",", "A2,Task2"])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201, r.text
    summary = r.json()["parse_summary"]
    assert summary["activities_created"] == 2
    assert summary["rows_skipped_blank"] >= 1


def test_a_gap_in_the_wbs_does_not_manufacture_a_false_root(client, test_project):
    """A row at 1.2.3 with no 1.2 present used to surface as a top-level node
    beside real L1 activities -- a flat list presented as a hierarchy."""
    pid, headers = test_project
    csv = make_csv(["ID,Name,WBS,Lvl", "A1,Top,1,1", "A2,Deep leaf,1.2.3,3"])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    tree = client.get(f"/api/v1/schedules/{sid}/activities/tree",
                      headers=headers).json()
    assert len(tree) == 1, f"expected one root, got {[n['activity_code'] for n in tree]}"
    assert tree[0]["activity_code"] == "A1"
    assert [c["activity_code"] for c in tree[0]["children"]] == ["A2"]
    assert r.json()["parse_summary"]["parents_relinked_to_ancestor"] == 1


def test_duplicate_wbs_paths_are_rejected(client, test_project):
    """Two rows claiming the same node makes parent linking arbitrary."""
    pid, headers = test_project
    csv = make_csv(["ID,Name,WBS,Lvl", "A1,First,1.1,2", "A2,Second,1.1,2"])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 400, r.text
    assert "1.1" in r.text


def test_dates_are_parsed_day_first_and_consistently(client, test_project):
    """03/04/2026 in an Indian or European export means 3 April. Month-first
    parsing turns that into a silent 30-day error."""
    pid, headers = test_project
    mapping = ('{"activity_code":"ID","name":"Name","planned_start":"S",'
               '"planned_finish":"F"}')
    csv = make_csv(["ID,Name,S,F",
                    "A1,First,03/04/2026,20/04/2026",
                    "A2,Second,05/04/2026,25/04/2026"])
    r = upload_schedule(client, pid, headers, csv, mapping=mapping)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    acts = client.get(f"/api/v1/schedules/{sid}/activities?limit=10",
                      headers=headers).json()["items"]
    by_code = {a["activity_code"]: a for a in acts}
    assert by_code["A1"]["planned_start"] == "2026-04-03"
    assert by_code["A1"]["planned_finish"] == "2026-04-20"
    assert by_code["A2"]["planned_start"] == "2026-04-05"


def test_unreadable_dates_are_counted_not_silently_blank(client, test_project):
    pid, headers = test_project
    mapping = '{"activity_code":"ID","name":"Name","planned_start":"S"}'
    csv = make_csv(["ID,Name,S", "A1,First,not a date at all"])
    r = upload_schedule(client, pid, headers, csv, mapping=mapping)
    assert r.status_code == 201, r.text
    summary = r.json()["parse_summary"]
    assert summary["dates_unparsed"] == 1
    assert any("could not be read as a date" in w for w in summary["warnings"])


def test_finish_before_start_is_rejected(client, test_project):
    pid, headers = test_project
    mapping = ('{"activity_code":"ID","name":"Name","planned_start":"S",'
               '"planned_finish":"F"}')
    csv = make_csv(["ID,Name,S,F", "A1,Backwards,2026-05-01,2026-01-01"])
    r = upload_schedule(client, pid, headers, csv, mapping=mapping)
    assert r.status_code == 400, r.text


def test_negative_budgeted_quantity_is_rejected(client, test_project):
    pid, headers = test_project
    mapping = '{"activity_code":"ID","name":"Name","budgeted_quantity":"Qty"}'
    csv = make_csv(["ID,Name,Qty", "A1,Task,-50"])
    r = upload_schedule(client, pid, headers, csv, mapping=mapping)
    assert r.status_code == 400, r.text


def test_a_long_dependency_chain_does_not_blow_the_stack(client, test_project):
    """A linear finish-to-start chain of a few thousand activities is routine
    on a pipeline. Recursive cycle detection raised RecursionError and
    reported it to the user as a file-content problem."""
    pid, headers = test_project
    lines = ["ID,Name,Pred", "C0,Start,"]
    for i in range(1, 1500):
        lines.append(f"C{i},Section {i},C{i - 1}")
    r = upload_schedule(client, pid, headers, make_csv(lines))
    assert r.status_code == 201, r.text[:400]
    assert r.json()["parse_summary"]["dependencies_created"] == 1499


def test_a_cycle_is_still_detected_by_the_iterative_check(client, test_project):
    pid, headers = test_project
    csv = make_csv(["ID,Name,Pred", "A1,One,A3", "A2,Two,A1", "A3,Three,A2"])
    r = upload_schedule(client, pid, headers, csv)
    assert r.status_code == 400, r.text
    assert "Circular dependency" in r.text


def test_a_schedule_id_from_another_project_is_not_reachable(
    client, test_project, manager_user, auth_headers
):
    """Authorising against the schedule's own project is not enough: a member
    of both projects could otherwise fetch B's schedule through A's URL."""
    pid_a, headers = test_project
    other = client.post("/api/v1/projects",
                        json={"code": "OTHER-SCHED", "name": "Other"},
                        headers=headers)
    assert other.status_code == 201
    pid_b = other.json()["id"]
    r = upload_schedule(client, pid_b, headers, make_csv(["ID,Name", "B1,Task"]))
    assert r.status_code == 201
    sid_b = r.json()["id"]

    leaked = client.get(f"/api/v1/projects/{pid_a}/schedules/{sid_b}", headers=headers)
    assert leaked.status_code == 404, leaked.text


def test_an_activity_from_another_schedule_is_not_reachable(client, test_project):
    pid, headers = test_project
    first = upload_schedule(client, pid, headers, make_csv(["ID,Name", "A1,Task"]))
    second = upload_schedule(client, pid, headers, make_csv(["ID,Name", "B1,Other"]))
    assert first.status_code == 201 and second.status_code == 201
    sid_1, sid_2 = first.json()["id"], second.json()["id"]

    acts_2 = client.get(f"/api/v1/schedules/{sid_2}/activities",
                        headers=headers).json()["items"]
    foreign_activity = acts_2[0]["id"]

    leaked = client.get(f"/api/v1/schedules/{sid_1}/activities/{foreign_activity}",
                        headers=headers)
    assert leaked.status_code == 404, leaked.text


def test_the_tree_is_not_truncated_by_the_pagination_cap(client, test_project):
    """The tree used to fetch a capped page, so any activity whose parent fell
    outside the window became a false root."""
    pid, headers = test_project
    lines = ["ID,Name,WBS,Lvl", "R,Root,1,1"]
    for i in range(1, 300):
        lines.append(f"A{i},Leaf {i},1.{i},2")
    r = upload_schedule(client, pid, headers, make_csv(lines))
    assert r.status_code == 201, r.text[:300]
    sid = r.json()["id"]

    tree = client.get(f"/api/v1/schedules/{sid}/activities/tree",
                      headers=headers).json()
    assert len(tree) == 1, f"{len(tree)} roots -- the tree was truncated"
    assert len(tree[0]["children"]) == 299


def test_iso_dates_are_not_misread_as_day_first(client, test_project):
    """2026-05-01 is unambiguously 1 May. An earlier fix applied dayfirst to
    the whole column, which made pandas return 5 January for ISO input -- a
    silent four-month error on the most common export format there is."""
    pid, headers = test_project
    mapping = ('{"activity_code":"ID","name":"Name","planned_start":"S",'
               '"planned_finish":"F"}')
    csv = make_csv(["ID,Name,S,F",
                    "A1,Iso,2026-05-01,2026-12-31",
                    "A2,Slash,03/04/2026,20/04/2026",
                    "A3,Named,01-Mar-2026,15-Mar-2026"])
    r = upload_schedule(client, pid, headers, csv, mapping=mapping)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    acts = client.get(f"/api/v1/schedules/{sid}/activities?limit=10",
                      headers=headers).json()["items"]
    by_code = {a["activity_code"]: a for a in acts}

    assert by_code["A1"]["planned_start"] == "2026-05-01"
    assert by_code["A1"]["planned_finish"] == "2026-12-31"
    # A slash date in the same column is still read day-first.
    assert by_code["A2"]["planned_start"] == "2026-04-03"
    # And a named month still parses.
    assert by_code["A3"]["planned_start"] == "2026-03-01"
    assert r.json()["parse_summary"]["dates_unparsed"] == 0


def test_a_real_legacy_xls_is_readable(client, test_project):
    """`.xls` is in the upload allowlist. The engine was pinned to openpyxl,
    which cannot read the legacy BIFF format at all, so every .xls upload
    failed with "File is not a zip file"."""
    xlwt = pytest.importorskip("xlwt")

    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")
    for column, header in enumerate(["ID", "Name", "WBS"]):
        sheet.write(0, column, header)
    sheet.write(1, 0, "A1"); sheet.write(1, 1, "Trenching"); sheet.write(1, 2, "1")
    sheet.write(2, 0, "A2"); sheet.write(2, 1, "Lowering"); sheet.write(2, 2, "1.1")
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    pid, headers = test_project
    r = client.post(
        f"/api/v1/projects/{pid}/schedules",
        files={"file": ("legacy.xls", buffer, "application/vnd.ms-excel")},
        data={"name": "Legacy",
              "mapping": '{"activity_code":"ID","name":"Name","wbs_path":"WBS"}'},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["parse_summary"]["activities_created"] == 2

    acts = client.get(f"/api/v1/schedules/{sid}/activities?limit=10",
                      headers=headers).json()["items"]
    paths = {a["activity_code"]: a["wbs_path"] for a in acts}
    # Excel hands back numbers; forcing the WBS column to text is what stops
    # 1.10 and 1.1 collapsing into the same float.
    assert paths == {"A1": "1", "A2": "1.1"}
