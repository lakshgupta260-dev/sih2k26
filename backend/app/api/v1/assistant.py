import hashlib
import uuid
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.project import ProjectMembership, Project
from app.models.schedule import Activity
from app.models.document import UploadedFile, ProcessingJob
from app.core.constants import DocumentType
from app.tasks.document_tasks import process_uploaded_file
from app.core.config import settings
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

async def get_user_projects(user: User, db: Session) -> list[uuid.UUID]:
    if not user:
        return []
    memberships = db.execute(
        select(ProjectMembership).where(ProjectMembership.user_id == user.id)
    ).scalars().all()
    return [m.project_id for m in memberships]


async def process_tool_call(function_name: str, arguments: Dict[str, Any], user: User | None, db: Session) -> str:
    """Execute a function call requested by the Vapi AI assistant."""
    if not user:
        return "Error: User is not authenticated or phone number not recognized."
        

    project_ids = await get_user_projects(user, db)
    if not project_ids:
        return "Error: You are not a member of any projects."
        
    if "project_id" in arguments and arguments["project_id"]:
        requested_pid = arguments["project_id"]
        # Make sure the user actually has access to the requested project
        if requested_pid in [str(pid) for pid in project_ids]:
            project_ids = [requested_pid]

        

    if function_name == "get_project_progress":
        from app.models.schedule import Schedule
        from app.models.schedule import Activity
        from app.models.prediction import DelayPrediction
        from app.core.constants import RiskLevel
        from sqlalchemy import select, func
        
        projects = db.execute(select(Project).where(Project.id.in_(project_ids))).scalars().all()
        summaries = []
        for p in projects:
            total_acts = db.execute(select(func.count(Activity.id)).join(Schedule).where(Schedule.project_id == p.id)).scalar() or 0
            critical_risks = db.execute(select(func.count(DelayPrediction.id)).where(DelayPrediction.project_id == p.id).where(DelayPrediction.risk_level == RiskLevel.CRITICAL)).scalar() or 0
            high_risks = db.execute(select(func.count(DelayPrediction.id)).where(DelayPrediction.project_id == p.id).where(DelayPrediction.risk_level == RiskLevel.HIGH)).scalar() or 0
            
            summary = f"*{p.name}*\n"
            summary += f"• Status: {p.status.upper()}\n"
            summary += f"• Timeline: {p.planned_start} to {p.planned_finish}\n"
            summary += f"• Activities: {total_acts} Total\n"
            if critical_risks > 0 or high_risks > 0:
                summary += f"• Risk Alert: {critical_risks} CRITICAL, {high_risks} HIGH risk activities predicted.\n"
            else:
                summary += f"• Risk Alert: No significant delays predicted.\n"
            summaries.append(summary)
            
        return "\n\n".join(summaries)

    elif function_name == "get_delayed_activities":
        import datetime as _dt

        from app.models.schedule import Schedule
        from app.models.progress import ActualProgress
        from app.core.constants import ActivityStatus

        today = _dt.date.today()

        # Candidates are activities whose planned finish has passed. Whether one
        # is actually late depends on its most recent reported progress, which
        # lives on ActualProgress (one row per activity per reporting date), so
        # the filtering happens below rather than in SQL.
        candidates = db.execute(
            select(Activity)
            .join(Schedule, Activity.schedule_id == Schedule.id)
            .where(Schedule.project_id.in_(project_ids))
            .where(Activity.planned_finish.is_not(None))
            .where(Activity.planned_finish < today)
            .order_by(Activity.planned_finish)
        ).scalars().all()

        if not candidates:
            return "No activities are past their planned finish date. Nothing is delayed right now."

        latest = db.execute(
            select(ActualProgress)
            .where(ActualProgress.activity_id.in_([a.id for a in candidates]))
            .order_by(ActualProgress.activity_id, ActualProgress.reporting_date.desc())
            .distinct(ActualProgress.activity_id)
        ).scalars().all()
        by_activity = {row.activity_id: row for row in latest}

        delayed_all = []
        for a in candidates:
            prog = by_activity.get(a.id)
            if prog is not None and prog.status == ActivityStatus.COMPLETED:
                continue  # finished, however late -- not outstanding work
            days_late = (today - a.planned_finish).days
            pct = prog.percent_complete if prog and prog.percent_complete is not None else 0
            delayed_all.append(
                f"{a.activity_code}, {a.name}: {days_late} days past planned finish, "
                f"{pct:.0f} percent complete."
            )

        if not delayed_all:
            return "Every activity past its planned finish date has been reported complete. Nothing is delayed."

        delayed_top5 = delayed_all[:5]
        header = f"There are {len(delayed_all)} total delayed activities on this project. Here are the worst {len(delayed_top5)}:\n"
        return header + "\n".join(delayed_top5)
        
    elif function_name == "get_risk_summary":
        from app.models.prediction import DelayPrediction
        from app.core.constants import RiskLevel
        
        all_rows = db.execute(
            select(DelayPrediction)
            .where(DelayPrediction.project_id.in_(project_ids))
            .where(DelayPrediction.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
            .order_by(DelayPrediction.probability.desc())
        ).scalars().all()
        
        if not all_rows:
            return ("No delay forecast has been generated for your projects yet. "
                    "Run a prediction from the dashboard and I can talk you through it.")

        top5 = all_rows[:5]

        # Name the activities. This is read aloud on a phone call, where a raw
        # UUID is unusable to the listener.
        names = {
            row.id: (row.activity_code, row.name)
            for row in db.execute(
                select(Activity.id, Activity.activity_code, Activity.name)
                .where(Activity.id.in_([r.activity_id for r in top5]))
            ).all()
        }

        lines = []
        for r in top5:
            code, name = names.get(r.activity_id, (None, None))
            label = f"{code}, {name}" if code else "an activity no longer in the schedule"
            line = f"{r.risk_level} risk on {label}: {r.probability:.0%} chance of finishing late"
            if r.forecast_slip_days:
                line += f", forecast slip {r.forecast_slip_days} days"
            lines.append(line + ".")
            
        header = f"There are {len(all_rows)} total activities at high or critical risk on this project. Here are the worst {len(top5)}:\n"
        return header + "\n".join(lines)
        
    elif function_name == "get_activity_details":
        from app.models.schedule import Schedule
        from app.models.progress import ActualProgress
        activity_code = arguments.get("activity_code")
        if not activity_code:
            return "Error: activity_code is required."
        activity = db.execute(
            select(Activity)
            .join(Schedule, Activity.schedule_id == Schedule.id)
            .where(Schedule.project_id.in_(project_ids))
            .where(Activity.activity_code == activity_code)
        ).scalar_one_or_none()
        if not activity:
            return f"Activity {activity_code} not found."
            
        prog = db.execute(
            select(ActualProgress)
            .where(ActualProgress.activity_id == activity.id)
            .order_by(ActualProgress.reporting_date.desc())
        ).scalars().first()
        status = prog.status if prog else "UNKNOWN"
        pct = prog.percent_complete if prog else 0
        
        return f"Activity {activity.activity_code}: {activity.name}. Status: {status}. Progress: {pct}%."
        
    elif function_name == "get_project_report":
        from app.services.reporting import ReportService
        from app.core.constants import GeneratedReportFormat
        try:
            ReportService(db).generate_report(
                project_id=project_ids[0],
                report_type="executive_overview",
                output_format=GeneratedReportFormat.PDF,
                parameters={},
                current_user=user
            )
            db.commit()
            return "The executive overview report has been generated and is now available in your project dashboard."
        except Exception as e:
            logger.error("Failed to generate report: %s", e)
            return f"Failed to generate report: {e}"
        
    else:
        return f"Error: Unknown tool {function_name}"


async def ingest_transcript(transcript: str, user: User, db: Session):
    """Ingest a call transcript into the document processing pipeline."""
    project_ids = await get_user_projects(user, db)
    if not project_ids:
        logger.warning("Cannot ingest transcript: User %s has no projects.", user.id)
        return
        
    project_id = project_ids[0] # Pick first project for MVP
    
    storage_path = f"voice_transcript_{uuid.uuid4().hex[:12]}.txt"
    uf = UploadedFile(
        project_id=project_id,
        uploaded_by_id=user.id,
        original_filename="vapi_call_transcript.txt",
        storage_path=storage_path,
        content_type="text/plain",
        size_bytes=len(transcript.encode('utf-8')),
        sha256=hashlib.sha256(transcript.encode('utf-8')).hexdigest(),
        document_type=DocumentType.OTHER
    )
    db.add(uf)
    db.flush()
    
    job = ProcessingJob(
        project_id=project_id,
        uploaded_file_id=uf.id,
    )
    db.add(job)
    db.commit()
    
    full_path = os.path.join(settings.UPLOAD_DIR, storage_path)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(transcript)
        
    process_uploaded_file.delay(str(job.id))
    logger.info("Ingested Vapi call transcript for project %s", project_id)
