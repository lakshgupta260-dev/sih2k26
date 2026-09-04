import logging
import hmac
import json
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


def verify_vapi_secret(x_vapi_secret: str | None, auth_header: str | None) -> bool:
    if not settings.VAPI_SECRET:
        logger.error("vapi_webhook_refused_no_secret_configured")
        return False
        
    secret_to_check = x_vapi_secret
    if not secret_to_check and auth_header and auth_header.startswith("Bearer "):
        secret_to_check = auth_header[7:]
        
    if not secret_to_check:
        return False
        
    return hmac.compare_digest(secret_to_check, settings.VAPI_SECRET)


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    x_vapi_secret: str = Header(None),
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    """Receive webhooks from Vapi (Server URL)."""
    if not verify_vapi_secret(x_vapi_secret, authorization):
        logger.warning("Invalid Vapi secret")
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    message = payload.get("message", {})
    msg_type = message.get("type")

    def _normalise_phone(raw: str) -> str:
        return "".join(ch for ch in raw if ch.isdigit())

    # Vapi sends caller info in call.customer.number
    customer_phone = message.get("call", {}).get("customer", {}).get("number", "")
    
    # Identify user and scoping
    user = None
    if customer_phone:
        user = db.execute(
            select(User).where(User.phone_normalised == _normalise_phone(customer_phone))
        ).scalars().first()

    if msg_type == "tool-calls":
        # Vapi is asking our backend to execute a tool/function
        tool_call_list = message.get("toolWithToolCallList") or message.get("toolCalls") or []
        results = []
        for item in tool_call_list:
            tool_call = item.get("toolCall", item)
            function_name = tool_call.get("function", {}).get("name")
            arguments = tool_call.get("function", {}).get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments or "{}")
            call_id = tool_call.get("id")
            
            try:
                result = await process_tool_call(function_name, arguments, user, db)
                logger.info(f"Tool {function_name} returned: {result}")
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
        
        logger.info(f"Sending back to Vapi: {results}")
        return {"results": results}

    elif msg_type == "end-of-call-report":
        # The call ended. We can ingest the transcript as a progress report.
        transcript = message.get("transcript")
        if transcript and user:
            await ingest_transcript(transcript, user, db)
            
        return Response(status_code=200)

    # For other message types (like assistant-request), just acknowledge
    return Response(status_code=200)
