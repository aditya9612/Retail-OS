from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.models.invoice import Invoice
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog
from app.schemas.whatsapp import (
    WhatsAppSettingUpdate,
    WhatsAppSettingResponse,
    WhatsAppSendInvoiceRequest,
    WhatsAppSendCustomRequest,
    WhatsAppTestRequest,
    WhatsAppLogResponse,
    WhatsAppLogListResponse,
)
from app.services.whatsapp_service import WhatsAppService
from app.tasks.whatsapp_tasks import (
    send_whatsapp_invoice_task,
    send_whatsapp_message_task,
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ==============================================================================
# 1. SETTINGS & CONFIGURATION
# ==============================================================================

@router.get(
    "/settings",
    response_model=WhatsAppSettingResponse,
    summary="Get Tenant WhatsApp Configuration",
    description="Retrieves the Meta WhatsApp Cloud API credentials and automations for the current organization.",
)
def get_whatsapp_settings(
    user: User = Depends(require_permission("stores:read")),
    db: Session = Depends(get_db),
):
    setting = (
        db.query(WhatsAppSetting)
        .filter(WhatsAppSetting.tenant_id == user.tenant_id, WhatsAppSetting.store_id.is_(None))
        .first()
    )

    if not setting:
        setting = WhatsAppSetting(
            tenant_id=user.tenant_id,
            store_id=None,
            is_enabled=True,
            auto_send_invoice=True,
            auto_send_order_confirm=True,
            template_invoice="pos_invoice_receipt",
            template_order_confirm="order_confirmation",
            template_language="en_US",
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)

    res = WhatsAppSettingResponse.model_validate(setting)
    res.has_access_token = bool(setting.access_token)
    return res


@router.put(
    "/settings",
    response_model=WhatsAppSettingResponse,
    summary="Update Tenant WhatsApp Configuration",
    description="Configures Meta Cloud API Phone Number ID, Access Token, WABA ID, and message templates.",
)
def update_whatsapp_settings(
    payload: WhatsAppSettingUpdate,
    user: User = Depends(require_permission("stores:write")),
    db: Session = Depends(get_db),
):
    setting = (
        db.query(WhatsAppSetting)
        .filter(WhatsAppSetting.tenant_id == user.tenant_id, WhatsAppSetting.store_id.is_(None))
        .first()
    )

    if not setting:
        setting = WhatsAppSetting(
            tenant_id=user.tenant_id,
            store_id=None,
        )
        db.add(setting)

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if field == "access_token" and not val:
            continue
        setattr(setting, field, val)

    db.commit()
    db.refresh(setting)

    res = WhatsAppSettingResponse.model_validate(setting)
    res.has_access_token = bool(setting.access_token)
    return res


# ==============================================================================
# 2. DISPATCH & TESTING
# ==============================================================================

@router.post(
    "/test",
    summary="Test Meta WhatsApp Connection",
    description="Sends a test ping or template message to verify Meta Cloud API credentials and recipient delivery.",
)
def test_whatsapp_connection(
    payload: WhatsAppTestRequest,
    user: User = Depends(require_permission("stores:write")),
    db: Session = Depends(get_db),
):
    service = WhatsAppService(db=db, tenant_id=user.tenant_id)
    if not service.is_configured:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp is not configured. Please supply Phone Number ID and Access Token in settings.",
        )

    if payload.template_name:
        res = service.send_raw_payload_sync(
            service.build_template_payload(
                to_phone=payload.recipient_phone,
                template_name=payload.template_name,
                language_code=service.template_language,
            )
        )
    else:
        test_msg = f"Retail-OS WhatsApp Integration Test: Verified successfully for Organization {user.tenant_id}!"
        res = service.send_message(payload.recipient_phone, test_msg)

    if res.get("status") == "failed":
        raise HTTPException(status_code=400, detail={"message": "WhatsApp test dispatch failed", "error": res.get("error")})

    return {"message": "Test message dispatched successfully", "result": res}


@router.post(
    "/send-invoice/{invoice_id}",
    summary="Dispatch Invoice via WhatsApp",
    description="Dispatches a tax invoice PDF receipt to the customer's WhatsApp number.",
)
def send_invoice_via_whatsapp(
    invoice_id: int,
    payload: Optional[WhatsAppSendInvoiceRequest] = None,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.tenant_id == user.tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    recipient_phone = payload.recipient_phone if payload else None
    custom_note = payload.custom_message if payload else None

    task = send_whatsapp_invoice_task.delay(
        tenant_id=user.tenant_id,
        invoice_id=invoice.id,
        recipient_phone=recipient_phone,
        custom_note=custom_note,
    )

    return {
        "message": f"Invoice {invoice.invoice_number} queued for WhatsApp delivery",
        "task_id": task.id,
        "invoice_id": invoice.id,
    }


@router.post(
    "/send",
    summary="Send Freeform WhatsApp Text Message",
    description="Legacy/Direct messaging endpoint for custom alerts.",
)
def send_message(
    data: WhatsAppSendCustomRequest,
    user: User = Depends(require_permission("orders:write")),
):
    task = send_whatsapp_message_task.delay(
        phone=data.phone,
        message=data.message,
        tenant_id=user.tenant_id,
    )
    return {"message": "WhatsApp message queued", "task_id": task.id}


# ==============================================================================
# 3. DELIVERY AUDIT LOGS
# ==============================================================================

@router.get(
    "/logs",
    response_model=WhatsAppLogListResponse,
    summary="List WhatsApp Delivery Logs",
    description="Lists delivery receipts, message states (sent, delivered, read, failed), and Meta message IDs.",
)
def list_whatsapp_logs(
    status: Optional[str] = Query(default=None, description="Filter by status: sent, delivered, read, failed"),
    message_type: Optional[str] = Query(default=None, description="Filter by type: invoice, order_confirmation, custom"),
    phone: Optional[str] = Query(default=None, description="Filter by recipient phone number"),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    query = db.query(WhatsAppLog).filter(WhatsAppLog.tenant_id == user.tenant_id)

    if status:
        query = query.filter(WhatsAppLog.status == status.lower())
    if message_type:
        query = query.filter(WhatsAppLog.message_type == message_type.lower())
    if phone:
        query = query.filter(WhatsAppLog.recipient_phone.contains(phone.strip()))
    if date_from:
        query = query.filter(WhatsAppLog.created_at >= date_from)
    if date_to:
        query = query.filter(WhatsAppLog.created_at <= date_to)

    total = query.count()
    items = (
        query.order_by(WhatsAppLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return WhatsAppLogListResponse(
        items=[WhatsAppLogResponse.model_validate(it) for it in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ==============================================================================
# 4. META CLOUD API WEBHOOKS
# ==============================================================================

@router.get(
    "/webhook",
    summary="Meta Cloud API Webhook Verification",
    description="Verifies Meta webhook challenge for subscriptions (hub.mode, hub.verify_token, hub.challenge).",
)
def verify_webhook(
    request: Request,
):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    verified_challenge = WhatsAppService().verify_webhook(mode, token, challenge)
    if verified_challenge is not None:
        return Response(content=str(verified_challenge), media_type="text/plain", status_code=200)

    raise HTTPException(status_code=403, detail="Webhook verification token mismatch")


@router.post(
    "/webhook",
    summary="Meta Cloud API Event Receiver",
    description="Receives real-time delivery statuses (delivered, read, failed) and incoming customer messages.",
)
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    service = WhatsAppService(db=db)
    return service.handle_webhook(payload)
