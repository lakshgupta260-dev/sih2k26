import logging
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.project import ProjectMembership
from app.api.v1.assistant import process_tool_call, ingest_transcript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/vapi", tags=["integrations"])


def verify_vapi_secret(x_vapi_secret: str) -> bool:
    if not settings.VAPI_SECRET:
        return True # If not configured, allow for testing/dev
    return x_vapi_secret == settings.VAPI_SECRET


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    x_vapi_secret: str = Header(None),
    db: Session = Depends(get_db),
):
    """Receive webhooks from Vapi (Server URL)."""
    if not verify_vapi_secret(x_vapi_secret):
        logger.warning("Invalid Vapi secret")
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    message = payload.get("message", {})
    msg_type = message.get("type")

    # In Vapi, caller phone number is often in call.customer.number
    call_obj = message.get("call", {})
    customer_phone = call_obj.get("customer", {}).get("number")
    
    # Identify user and scoping
    user = None
    if customer_phone:
        # Simple match for MVP
        user = db.execute(
            select(User).where(User.phone.like(f"%{customer_phone.lstrip('+')}%"))
        ).scalars().first()

    if msg_type == "tool-calls":
        # Vapi is asking our backend to execute a tool/function
        tool_with_tool_call_list = message.get("toolCalls", [])
        results = []
        for tool_call in tool_with_tool_call_list:
            function_name = tool_call.get("function", {}).get("name")
            arguments = tool_call.get("function", {}).get("arguments", {})
            call_id = tool_call.get("id")
            
            try:
                result = await process_tool_call(function_name, arguments, user, db)
                results.append({
                    "toolCallId": call_id,
                    "result": result
                })
            except Exception as e:
                logger.exception(f"Error executing tool {function_name}")
                results.append({
                    "toolCallId": call_id,
                    "error": str(e)
                })
        
        return {"results": results}

    elif msg_type == "end-of-call-report":
        # The call ended. We can ingest the transcript as a progress report.
        transcript = message.get("transcript")
        if transcript and user:
            await ingest_transcript(transcript, user, db)
            
        return Response(status_code=200)

    # For other message types (like assistant-request), just acknowledge
    return Response(status_code=200)
