import hashlib
import hmac
import logging
import uuid
import datetime
import io
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.project import Project, ProjectMembership
from app.models.document import UploadedFile, ProcessingJob
from app.core.constants import DocumentType
from app.tasks.document_tasks import process_uploaded_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/meta", tags=["integrations"])


def verify_meta_signature(payload: bytes, signature: str) -> bool:
    """Verify the X-Hub-Signature-256 header."""
    if not settings.META_APP_SECRET or not signature:
        return False
    expected = hmac.new(
        settings.META_APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None,
):
    """Meta webhook verification endpoint."""
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify_token")

    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        logger.info("Meta webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("Failed Meta webhook verification.")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    db: Session = Depends(get_db),
):
    """Receive messages from WhatsApp."""
    payload = await request.body()
    
    # Check signature if META_APP_SECRET is set
    if settings.META_APP_SECRET:
        if not verify_meta_signature(payload, x_hub_signature_256):
            logger.warning("Invalid Meta webhook signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    
    # Return 200 OK immediately as required by Meta
    if data.get("object") != "whatsapp_business_account":
        return Response(status_code=200)

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            
            # We only care about messages
            if "messages" not in value:
                continue
                
            contacts = {c["wa_id"]: c for c in value.get("contacts", [])}
            
            for msg in value["messages"]:
                if msg.get("type") != "text":
                    continue # For MVP, only handle text
                    
                sender_wa_id = msg.get("from")
                text_body = msg.get("text", {}).get("body", "").strip()
                
                # Phone matching (WhatsApp provides format like 1234567890, we match on endswith or strip)
                # To be safe, we match where user.phone contains the sender_wa_id or vice versa
                user = db.execute(
                    select(User).where(User.phone.like(f"%{sender_wa_id}%"))
                ).scalars().first()
                
                if not user:
                    logger.warning("WhatsApp message from unknown phone: %s", sender_wa_id)
                    continue
                    
                # Find project. For MVP, we take the first project they are in
                membership = db.execute(
                    select(ProjectMembership).where(ProjectMembership.user_id == user.id)
                ).scalars().first()
                
                if not membership:
                    logger.warning("User %s is not in any projects", user.id)
                    continue
                    
                project_id = membership.project_id
                
                # Create UploadedFile
                storage_path = f"wa_msg_{uuid.uuid4().hex[:12]}.txt"
                uf = UploadedFile(
                    project_id=project_id,
                    uploaded_by_id=user.id,
                    original_filename="whatsapp_message.txt",
                    storage_path=storage_path,
                    content_type="text/plain",
                    size_bytes=len(text_body.encode('utf-8')),
                    sha256=hashlib.sha256(text_body.encode('utf-8')).hexdigest(),
                    document_type=DocumentType.OTHER
                )
                db.add(uf)
                db.flush()
                
                # Create processing job
                job = ProcessingJob(
                    project_id=project_id,
                    uploaded_file_id=uf.id,
                )
                db.add(job)
                db.commit()
                
                # Save text body to storage_path (just mock or write to actual storage)
                import os
                full_path = os.path.join(settings.UPLOAD_DIR, storage_path)
                os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(text_body)
                    
                # Trigger Celery parsing task
                process_uploaded_file.delay(str(job.id))
                logger.info("Ingested WhatsApp message from %s for project %s", sender_wa_id, project_id)

    return Response(status_code=200)
