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
        
    if function_name == "query_project_status":
        # AI wants to know general project status
        projects = db.execute(
            select(Project).where(Project.id.in_(project_ids))
        ).scalars().all()
        
        status_info = []
        for p in projects:
            status_info.append(f"Project: {p.name} (ID: {p.id}), Status: {p.status}")
        return "\n".join(status_info)
        
    elif function_name == "query_activity_status":
        # AI wants to know about a specific activity
        activity_code = arguments.get("activity_code")
        if not activity_code:
            return "Error: activity_code is required."
            
        activity = db.execute(
            select(Activity)
            .join(Project, Activity.project_id == Project.id)
            .where(Activity.project_id.in_(project_ids))
            .where(Activity.activity_code == activity_code)
        ).scalar_one_or_none()
        
        if not activity:
            return f"Activity {activity_code} not found in your authorized projects."
            
        return f"Activity {activity.activity_code}: {activity.name}. Status: {activity.status}. Planned Finish: {activity.planned_finish}."
        
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
