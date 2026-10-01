from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.security import require_permission
from app.models.user import User
from app.services.whatsapp_service import WhatsAppService
from app.tasks.whatsapp_tasks import send_whatsapp_message_task

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


class WhatsAppSendRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/send")
async def send_message(
    data: WhatsAppSendRequest,
    user: User = Depends(require_permission("orders:write")),
):
    task = send_whatsapp_message_task.delay(data.phone, data.message)
    return {"task_id": task.id}


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    return WhatsAppService().handle_webhook(payload)
