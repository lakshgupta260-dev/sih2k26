"""Phase 4 tests — upload validation, document processors, async processing task, documents and reports APIs."""
from __future__ import annotations

import io
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import DocumentType, JobStatus, UserRole
from app.core.exceptions import UnprocessableFileError, ValidationError
from app.document_processing.processors import (
    CSVProcessor,
    ExcelProcessor,
    NoopOCRProcessor,
    PDFProcessor,
    TextProcessor,
    processor_for,
)
from app.models.document import ProcessingJob, ProgressReport, UploadedFile
from app.services.document import DocumentService, UploadValidator
from app.tasks.document_tasks import process_uploaded_file

PROJECTS = "/api/v1/projects"


def _create_project(client: TestClient, headers: dict) -> str:
    body = {
        "code": f"PROJ-DOC-{uuid.uuid4().hex[:6]}",
        "name": "Document Processing Test Project",
        "description": "Test project for document processing",
        "client_name": "Test Client",
        "location": "Delhi",
        "planned_start": "2026-01-01",
        "planned_finish": "2026-12-31",
    }
    res = client.post(PROJECTS, json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["id"]


# -------------------------------------------------------------------- 1. UploadValidator Unit Tests
def test_upload_validator_valid_csv() -> None:
    content = b"ActivityID,Name,Progress\nACT-1,Excavation,50\n"
    name, mime = UploadValidator.validate("progress.csv", "text/csv", content)
    assert name == "progress.csv"
    assert mime == "text/csv"


def test_upload_validator_empty_file() -> None:
    with pytest.raises(ValidationError) as exc:
        UploadValidator.validate("test.csv", "text/csv", b"")
    assert exc.value.code == "EMPTY_FILE"


def test_upload_validator_file_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    large_content = b"x" * (1024 * 1024 + 1)
    with pytest.raises(ValidationError) as exc:
        UploadValidator.validate("test.txt", "text/plain", large_content)
    assert exc.value.code == "FILE_TOO_LARGE"


def test_upload_validator_unsupported_extension() -> None:
    with pytest.raises(ValidationError) as exc:
        UploadValidator.validate("script.exe", "application/octet-stream", b"binary")
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_upload_validator_pdf_magic_bytes_mismatch() -> None:
    with pytest.raises(ValidationError) as exc:
        UploadValidator.validate("doc.pdf", "application/pdf", b"NOT A PDF FILE")
    assert exc.value.code == "MAGIC_BYTES_MISMATCH"


# -------------------------------------------------------------------- 2. Document Processors Unit Tests
def test_processor_factory_selection(tmp_path: Path) -> None:
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("Hello World")
    proc = processor_for(txt_file)
    assert isinstance(proc, TextProcessor)
    res = proc.process(txt_file)
    assert res.raw_text == "Hello World"


def test_csv_processor(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_content = "ActivityID,Status,Percent\nACT-101,Complete,100\nACT-102,In Progress,40\n"
    csv_file.write_text(csv_content)

    proc = CSVProcessor()
    res = proc.process(csv_file)
    assert "ACT-101" in res.raw_text
    assert res.metadata["rows"] == 2
    assert res.metadata["columns"] == ["ActivityID", "Status", "Percent"]


def test_unsupported_processor_extension(tmp_path: Path) -> None:
    unknown_file = tmp_path / "sample.unknown"
    unknown_file.write_text("content")
    with pytest.raises(UnprocessableFileError):
        processor_for(unknown_file)


# -------------------------------------------------------------------- 3. API & Task Integration Tests
def test_document_upload_job_polling_and_report_retrieval(
    client: TestClient,
    admin_user,
    auth_headers,
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_task_with_test_session,
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    headers = auth_headers(admin_user)
    project_id = _create_project(client, headers)

    # 1. Upload CSV document
    csv_bytes = b"ActivityID,Name,Progress\nACT-1,Foundation,100\nACT-2,Piling,80\n"
    files = {"file": ("dpr_report.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"document_type": DocumentType.DAILY_PROGRESS_REPORT.value}

    response = client.post(f"{PROJECTS}/{project_id}/documents", files=files, data=data, headers=headers)
    assert response.status_code == 202, response.text
    body = response.json()

    uploaded_file_id = body["file"]["id"]
    job_id = body["job"]["id"]

    assert body["file"]["original_filename"] == "dpr_report.csv"
    assert body["job"]["status"] in [JobStatus.PENDING, JobStatus.COMPLETED]

    # 2. Get document detail
    doc_res = client.get(f"{PROJECTS}/{project_id}/documents/{uploaded_file_id}", headers=headers)
    assert doc_res.status_code == 200
    assert doc_res.json()["id"] == uploaded_file_id

    # 3. List project documents
    docs_res = client.get(f"{PROJECTS}/{project_id}/documents", headers=headers)
    assert docs_res.status_code == 200
    assert docs_res.json()["total"] == 1

    # 4. Process job explicitly via task (simulating Celery worker execution).
    #    The task opens its own SessionLocal, as a real worker must; redirect it
    #    at the test session so it can see this test's uncommitted rows.
    import app.tasks.document_tasks as document_tasks

    run_task_with_test_session(document_tasks)
    process_uploaded_file(job_id)

    # 5. Check job status endpoint
    job_res = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_res.status_code == 200
    job_info = job_res.json()
    assert job_info["status"] == JobStatus.COMPLETED.value
    assert job_info["processor"] == "csv"

    # 6. List and get generated progress reports
    reports_res = client.get(f"{PROJECTS}/{project_id}/reports", headers=headers)
    assert reports_res.status_code == 200
    reports_data = reports_res.json()
    assert reports_data["total"] == 1
    report_id = reports_data["items"][0]["id"]

    report_detail_res = client.get(f"{PROJECTS}/{project_id}/reports/{report_id}", headers=headers)
    assert report_detail_res.status_code == 200
    report_body = report_detail_res.json()
    assert "ACT-1" in report_body["raw_text"]
    assert report_body["extracted_data"]["rows"] == 2


def test_tenant_isolation_on_documents_and_reports(
    client: TestClient, admin_user, supervisor_user, auth_headers, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    admin_hdrs = auth_headers(admin_user)
    supervisor_hdrs = auth_headers(supervisor_user)

    project_id = _create_project(client, admin_hdrs)

    # Upload file as Admin
    csv_bytes = b"Col1,Col2\nVal1,Val2\n"
    files = {"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post(f"{PROJECTS}/{project_id}/documents", files=files, headers=admin_hdrs)
    assert upload_res.status_code == 202

    # An unenrolled user must get 404, not 403. Confirming that a project id
    # exists is itself a leak across the tenancy boundary, so project access
    # resolves to NotFound rather than PermissionDenied -- the same convention
    # /projects/{id} follows (see backend/README.md, Authorization model).
    forbidden_docs = client.get(f"{PROJECTS}/{project_id}/documents", headers=supervisor_hdrs)
    assert forbidden_docs.status_code == 404

    forbidden_reports = client.get(f"{PROJECTS}/{project_id}/reports", headers=supervisor_hdrs)
    assert forbidden_reports.status_code == 404
