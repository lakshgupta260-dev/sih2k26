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
    if not settings.META_APP_SECRET:
        logger.error("meta_webhook_refused_no_app_secret_configured")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if not signature:
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

    logger.info("meta_webhook_verification", extra={"matched": hub_verify_token == settings.META_VERIFY_TOKEN})

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
    
    if not verify_meta_signature(payload, x_hub_signature_256):
        logger.warning("meta_webhook_invalid_signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    logger.debug("meta_webhook_received", extra={"entries": len(data.get("entry", []))})
    
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
                msg_type = msg.get("type")
                sender_wa_id = msg.get("from")
                wa_message_id = msg.get("id")
                
                if wa_message_id:
                    already = db.execute(
                        select(UploadedFile).where(UploadedFile.provider_message_id == wa_message_id)
                    ).scalars().first()
                    if already:
                        logger.info("whatsapp_message_already_ingested", extra={"wamid": wa_message_id})
                        continue
                
                if msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    if interactive.get("type") == "button_reply":
                        button_id = interactive.get("button_reply", {}).get("id")
                        if button_id == "call_ai":
                            logger.info("User clicked Call AI Assistant!")
                            if settings.VAPI_API_KEY:
                                import httpx
                                vapi_url = "https://api.vapi.ai/call/phone"
                                vapi_payload = {
                                    "phoneNumberId": getattr(settings, "VAPI_PHONE_NUMBER_ID", "f662a968-e48c-4108-b465-c796b45b06a0"),
                                    "assistantId": getattr(settings, "VAPI_ASSISTANT_ID", "3f8b2238-7fc3-4d0d-9324-e35f3f53af9b"),
                                    "customer": {
                                        "number": f"+{sender_wa_id}"
                                    }
                                }
                                vapi_headers = {
                                    "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                                    "Content-Type": "application/json"
                                }
                                try:
                                    async with httpx.AsyncClient(timeout=10.0) as client:
                                        res = await client.post(vapi_url, json=vapi_payload, headers=vapi_headers)
                                        logger.info("Vapi call triggered, status: %s", res.status_code)
                                except Exception as e:
                                    logger.error("Failed to call Vapi: %s", e)
                            continue

                if msg_type != "text":
                    continue # For MVP, only handle text
                    
                text_body = msg.get("text", {}).get("body", "").strip()
                
                def _normalise_phone(raw: str) -> str:
                    return "".join(ch for ch in raw if ch.isdigit())

                user = db.execute(
                    select(User).where(User.phone_normalised == _normalise_phone(sender_wa_id))
                ).scalars().first()
                
                if not user:
                    logger.warning("WhatsApp message from unknown phone: %s", sender_wa_id)
                    continue
                    
                # Find project. For MVP, we take the first project they are in
                membership = db.execute(
                    select(ProjectMembership).where(ProjectMembership.user_id == user.id).order_by(ProjectMembership.project_id)
                ).scalars().first()
                
                if not membership:
                    logger.warning("User %s is not in any projects", user.id)
                    continue
                    
                project_id = membership.project_id
                
                # Create UploadedFile
                msg_id = f"wa_msg_{uuid.uuid4().hex[:12]}"
                storage_path = f"{project_id}/{msg_id}.txt"
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
                
                import os
                full_path = os.path.join(settings.UPLOAD_DIR, storage_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(text_body)
                    
                db.commit()
                
                # Trigger Celery parsing task
                try:
                    process_uploaded_file.delay(str(job.id))
                except Exception as exc:
                    logger.exception("whatsapp_job_not_queued", extra={"job_id": str(job.id)})
                    job.status = "FAILED" # Note: JobStatus.FAILED if imported
                    job.error_message = f"Could not queue for processing: {exc}"[:4000]
                    db.commit()
                logger.info("Ingested WhatsApp message from %s for project %s", sender_wa_id, project_id)

    return Response(status_code=200)
