"""Report generation service."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import GeneratedReportFormat, GeneratedReportStatus, UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.schedule import Activity
from app.models.project import Project, ProjectMembership
from app.models.reporting import GeneratedReport
from app.models.user import User
from app.reports.excel_builder import ExcelReportBuilder
from app.reports.pdf_builder import PDFReportBuilder


class ReportService:
    """Business logic for generating, persisting, listing, and downloading project reports."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _ensure_access(self, project_id: uuid.UUID, user: User) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found")

        if user.role != UserRole.ADMIN:
            membership = self.db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user.id,
                )
            )
            if not membership:
                raise NotFoundError("Project not found")

        return project

    def list_reports(
        self, project_id: uuid.UUID, current_user: User, *, skip: int = 0, limit: int = 50
    ) -> tuple[list[GeneratedReport], int]:
        self._ensure_access(project_id, current_user)

        query = select(GeneratedReport).where(GeneratedReport.project_id == project_id)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = self.db.scalars(
            query.order_by(GeneratedReport.created_at.desc()).offset(skip).limit(limit)
        ).all()
        return list(items), total

    def get_report(
        self, project_id: uuid.UUID, report_id: uuid.UUID, current_user: User
    ) -> GeneratedReport:
        self._ensure_access(project_id, current_user)
        report = self.db.get(GeneratedReport, report_id)
        if not report or report.project_id != project_id:
            raise NotFoundError("Report not found")
        return report

    def _gather_project_snapshot(
        self, project_id: uuid.UUID, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Collect current project metrics for rendering the report."""
        discipline = parameters.get("discipline")
        status_filter = parameters.get("status")

        query = select(Activity).where(Activity.project_id == project_id)
        if discipline:
            query = query.where(Activity.discipline == discipline)
        if status_filter:
            query = query.where(Activity.status == status_filter)

        activities = self.db.scalars(query.order_by(Activity.activity_code.asc())).all()

        total = len(activities)
        completed = sum(1 for a in activities if a.status == "COMPLETED")
        in_progress = sum(1 for a in activities if a.status == "IN_PROGRESS")
        delayed = sum(1 for a in activities if a.actual_duration and a.planned_duration and a.actual_duration > a.planned_duration)
        high_risk = sum(1 for a in activities if getattr(a, "risk_band", "LOW") in ("HIGH", "CRITICAL"))

        progress_sum = sum(float(a.progress_pct or 0.0) for a in activities)
        progress_pct = (progress_sum / total) if total > 0 else 0.0

        activity_data = [
            {
                "code": a.activity_code,
                "name": a.name,
                "discipline": a.discipline or "",
                "wbs_path": a.wbs_path or "",
                "status": a.status or "NOT_STARTED",
                "progress_pct": float(a.progress_pct or 0.0),
                "risk_band": getattr(a, "risk_band", "LOW"),
            }
            for a in activities
        ]

        return {
            "title": f"Project Progress & Delay Risk Report",
            "summary": {
                "total_activities": total,
                "completed_activities": completed,
                "in_progress_activities": in_progress,
                "delayed_activities": delayed,
                "high_risk_count": high_risk,
                "progress_pct": round(progress_pct, 1),
            },
            "activities": activity_data,
            "risks": [
                {
                    "code": a.activity_code,
                    "name": a.name,
                    "risk_score": float(getattr(a, "risk_score", 0.1)),
                    "risk_band": getattr(a, "risk_band", "LOW"),
                    "forecast_delay_days": int(getattr(a, "forecast_delay_days", 0)),
                    "top_factors": "Schedule baseline variance",
                }
                for a in activities
                if getattr(a, "risk_band", "LOW") in ("MEDIUM", "HIGH", "CRITICAL")
            ],
        }

    def generate_report(
        self,
        project_id: uuid.UUID,
        report_type: str,
        output_format: GeneratedReportFormat,
        parameters: dict[str, Any],
        current_user: User,
    ) -> GeneratedReport:
        project = self._ensure_access(project_id, current_user)

        if report_type not in ("progress_summary", "delay_risk", "executive_overview"):
            raise ValidationError(f"Unsupported report type: {report_type}")

        # Create record in PENDING state
        report = GeneratedReport(
            project_id=project_id,
            requested_by_id=current_user.id,
            report_type=report_type,
            output_format=output_format,
            status=GeneratedReportStatus.PENDING,
            parameters=parameters,
            snapshot={},
        )
        self.db.add(report)
        self.db.flush()

        try:
            snapshot = self._gather_project_snapshot(project_id, parameters)
            report.snapshot = snapshot

            # Render binary content using builder
            if output_format == GeneratedReportFormat.PDF:
                builder = PDFReportBuilder(project.name, parameters)
                file_bytes = builder.build(snapshot)
                extension = ".pdf"
                content_type = "application/pdf"
            elif output_format == GeneratedReportFormat.XLSX:
                builder = ExcelReportBuilder(project.name, parameters)
                file_bytes = builder.build(snapshot)
                extension = ".xlsx"
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                raise ValidationError(f"Unsupported format: {output_format}")

            sha256 = hashlib.sha256(file_bytes).hexdigest()
            filename = f"report_{project_id.hex[:8]}_{report.id.hex[:8]}{extension}"
            
            storage_dir = Path(settings.GENERATED_REPORTS_DIR)
            storage_dir.mkdir(parents=True, exist_ok=True)
            file_path = storage_dir / filename
            file_path.write_bytes(file_bytes)

            report.storage_path = str(file_path)
            report.filename = filename
            report.content_type = content_type
            report.size_bytes = len(file_bytes)
            report.sha256 = sha256
            report.status = GeneratedReportStatus.COMPLETED
            report.generated_at = func.now()

        except Exception as exc:
            report.status = GeneratedReportStatus.FAILED
            report.error_message = str(exc)
            self.db.commit()
            raise

        self.db.commit()
        self.db.refresh(report)
        return report

    def get_report_file_path(
        self, project_id: uuid.UUID, report_id: uuid.UUID, current_user: User
    ) -> tuple[Path, str, str]:
        report = self.get_report(project_id, report_id, current_user)
        if report.status != GeneratedReportStatus.COMPLETED or not report.storage_path:
            raise ValidationError("Report is not ready for download")

        file_path = Path(report.storage_path)
        if not file_path.exists():
            raise NotFoundError("Report binary artifact missing from storage")

        filename = report.filename or f"report{Path(report.storage_path).suffix}"
        content_type = report.content_type or "application/octet-stream"
        return file_path, filename, content_type
