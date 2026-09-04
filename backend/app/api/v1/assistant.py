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
        
    if function_name == "get_project_progress":
        projects = db.execute(select(Project).where(Project.id.in_(project_ids))).scalars().all()
        return "\n".join([f"Project {p.name}: Status is {p.status}. Start: {p.planned_start}, Finish: {p.planned_finish}." for p in projects])
        
    elif function_name == "get_delayed_activities":
        from app.models.schedule import Schedule
        from app.models.progress import ActualProgress
        activities = db.execute(
            select(Activity)
            .join(Schedule, Activity.schedule_id == Schedule.id)
            .where(Schedule.project_id.in_(project_ids))
            .limit(5)
        ).scalars().all()
        
        if not activities:
            return "No delayed activities found."
            
        latest = db.execute(
            select(ActualProgress)
            .where(ActualProgress.activity_id.in_([a.id for a in activities]))
            .order_by(ActualProgress.activity_id, ActualProgress.reporting_date.desc())
            .distinct(ActualProgress.activity_id)
        ).scalars().all() if activities else []
        by_activity = {row.activity_id: row for row in latest}
        
        res = []
        for a in activities:
            prog = by_activity.get(a.id)
            status = prog.status if prog else "UNKNOWN"
            res.append(f"Activity {a.activity_code} ({a.name}): Status {status}.")
        return "\n".join(res)
        
    elif function_name == "get_risk_summary":
        from app.models.prediction import DelayPrediction
        from app.core.constants import RiskLevel
        rows = db.execute(
            select(DelayPrediction)
            .where(DelayPrediction.project_id.in_(project_ids))
            .where(DelayPrediction.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
            .order_by(DelayPrediction.probability.desc())
            .limit(5)
        ).scalars().all()
        
        if not rows:
            return ("No delay forecast has been generated for your projects yet. "
                    "Run a prediction from the dashboard and I can talk you through it.")
                    
        lines = [
            f"{r.risk_level} risk on activity {r.activity_id}: "
            f"{r.probability:.0%} chance of finishing late"
            + (f", forecast slip {r.forecast_slip_days} days" if r.forecast_slip_days else "")
            for r in rows
        ]
        return "Top delay risks:\n" + "\n".join(lines)
        
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
