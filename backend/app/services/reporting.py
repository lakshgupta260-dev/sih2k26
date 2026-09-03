"""Report generation service."""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    ActivityStatus,
    GeneratedReportFormat,
    GeneratedReportStatus,
    RiskLevel,
    UserRole,
)
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.prediction import DelayPrediction
from app.models.progress import ActualProgress
from app.models.schedule import Activity, Schedule
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

        # Activity has no project_id of its own -- it belongs to a schedule,
        # and the schedule belongs to the project. Filtering Activity directly
        # by project_id doesn't exist as a column and previously raised
        # AttributeError on every single call, so every report generation
        # request failed with a 500 before this fix.
        query = (
            select(Activity)
            .join(Schedule, Activity.schedule_id == Schedule.id)
            .where(Schedule.project_id == project_id)
        )
        if discipline:
            query = query.where(Activity.discipline == discipline)

        activities = self.db.scalars(query.order_by(Activity.activity_code.asc())).all()
        activity_ids = [a.id for a in activities]

        # Status and percent-complete are not columns on Activity at all --
        # they live on ActualProgress, one row per activity per reporting
        # date (see app/services/progress.py, which this mirrors). The prior
        # implementation read a.status / a.progress_pct / a.actual_duration /
        # a.planned_duration directly off Activity, none of which exist, so
        # every one of those reads raised AttributeError the moment a real
        # activity reached this code (masked in the original tests, which
        # never seeded any activities). Rows are pulled ascending by
        # reporting_date so the last write per activity_id is the latest one.
        latest_progress: dict[uuid.UUID, ActualProgress] = {}
        if activity_ids:
            progress_rows = self.db.scalars(
                select(ActualProgress)
                .where(ActualProgress.activity_id.in_(activity_ids))
                .order_by(ActualProgress.reporting_date.asc())
            ).all()
            for row in progress_rows:
                latest_progress[row.activity_id] = row

        if status_filter:
            activities = [
                a
                for a in activities
                if (latest_progress.get(a.id).status if latest_progress.get(a.id) else ActivityStatus.NOT_STARTED)
                == status_filter
            ]

        # Real delay-risk data lives in delay_predictions (Phase 7), keyed by
        # activity_id. The prior implementation read risk_band/risk_score/
        # forecast_delay_days straight off Activity via getattr(..., default),
        # attributes that don't exist on the model -- every activity silently
        # fell back to the default, so every report always showed "LOW" risk
        # and an empty risk table no matter what the ML/rule-based predictor
        # actually forecast. Joining the real prediction rows instead of
        # fabricating them is required by this project's no-fake-AI rule.
        predictions_by_activity: dict[uuid.UUID, DelayPrediction] = {}
        if activity_ids:
            rows = self.db.scalars(
                select(DelayPrediction).where(DelayPrediction.activity_id.in_(activity_ids))
            ).all()
            predictions_by_activity = {p.activity_id: p for p in rows}

        today = date.today()

        def _status_of(activity: Activity) -> str:
            progress = latest_progress.get(activity.id)
            return progress.status if progress is not None else ActivityStatus.NOT_STARTED

        def _percent_of(activity: Activity) -> float:
            progress = latest_progress.get(activity.id)
            if progress is None or progress.percent_complete is None:
                return 0.0
            return float(progress.percent_complete)

        def _is_delayed(activity: Activity) -> bool:
            progress = latest_progress.get(activity.id)
            if activity.planned_finish is None:
                return False
            if progress is not None and progress.actual_finish is not None:
                return progress.actual_finish > activity.planned_finish
            status = _status_of(activity)
            return status != ActivityStatus.COMPLETED and activity.planned_finish < today

        total = len(activities)
        completed = sum(1 for a in activities if _status_of(a) == ActivityStatus.COMPLETED)
        in_progress = sum(1 for a in activities if _status_of(a) == ActivityStatus.IN_PROGRESS)
        delayed = sum(1 for a in activities if _is_delayed(a))
        high_risk = sum(
            1
            for a in activities
            if predictions_by_activity.get(a.id) is not None
            and predictions_by_activity[a.id].risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )

        progress_sum = sum(_percent_of(a) for a in activities)
        progress_pct = (progress_sum / total) if total > 0 else 0.0

        activity_data = [
            {
                "code": a.activity_code,
                "name": a.name,
                "discipline": a.discipline or "",
                "wbs_path": a.wbs_path or "",
                "status": _status_of(a),
                "progress_pct": _percent_of(a),
                "risk_band": (
                    predictions_by_activity[a.id].risk_level
                    if predictions_by_activity.get(a.id) is not None
                    else "NOT_FORECASTED"
                ),
            }
            for a in activities
        ]

        risks = []
        for a in activities:
            prediction = predictions_by_activity.get(a.id)
            if prediction is None or prediction.risk_level not in (
                RiskLevel.MEDIUM,
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            ):
                continue
            top_factor = "Schedule baseline variance"
            if prediction.explanation:
                factors = prediction.explanation.get("top_factors")
                if factors:
                    top_factor = ", ".join(str(f) for f in factors[:3])
            risks.append(
                {
                    "code": a.activity_code,
                    "name": a.name,
                    "risk_score": float(prediction.probability),
                    "risk_band": prediction.risk_level,
                    "forecast_delay_days": int(prediction.forecast_slip_days or 0),
                    "top_factors": top_factor,
                }
            )

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
            "risks": risks,
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
