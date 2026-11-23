import base64
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.user import User
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog, KhataFollowup
from app.schemas.whatsapp import (
    HandwrittenGroceryOcrRequest,
    HandwrittenGroceryOcrResponse,
    KhataFollowupListResponse,
    KhataFollowupResponse,
    KhataPendingCustomerItem,
    KhataProcessReplyRequest,
    KhataReminderBroadcastRequest,
    KhataReminderRequest,
    WhatsAppChatOrderRequest,
    WhatsAppChatOrderResponse,
    WhatsAppLogListResponse,
    WhatsAppLogResponse,
    WhatsAppSendCustomRequest,
    WhatsAppSendInvoiceRequest,
    WhatsAppSettingResponse,
    WhatsAppSettingUpdate,
    WhatsAppTestRequest,
)
from app.services.smart_khata_service import SmartKhataService
from app.services.whatsapp_ordering_service import WhatsAppOrderingService
from app.services.whatsapp_service import WhatsAppService
from app.tasks.whatsapp_tasks import (
    broadcast_khata_reminders_task,
    send_khata_reminder_task,
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
            ai_ordering_enabled=True,
            ai_ocr_grocery_enabled=True,
            ai_khata_reminders_enabled=True,
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
    user: User = Depends(require_permission("stores:update")),
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
    user: User = Depends(require_permission("stores:create")),
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
    user: User = Depends(require_permission("orders:create")),
):
    task = send_whatsapp_message_task.delay(
        phone=data.phone,
        message=data.message,
        tenant_id=user.tenant_id,
    )
    return {"message": "WhatsApp message queued", "task_id": task.id}


# ==============================================================================
# 3. AI FEATURE 1: "कागदी किराणा चिठ्ठी" OCR BOT (Handwritten List to Cart/Order)
# ==============================================================================

@router.post(
    "/ocr-grocery-list",
    response_model=HandwrittenGroceryOcrResponse,
    summary="Handwritten Grocery List OCR to Cart/Order",
    description=(
        "Uses Gemini Multimodal Vision AI to read messy handwritten paper grocery lists "
        "(किराणा मालाची चिठ्ठी/पर्ची) in Marathi, Hindi, or English. Extracts items, quantities, "
        "regional fractions (पाव, अर्धा, पाऊण, दीड, अडीच), maps them to store inventory, "
        "creates an order/cart, and generates an instant UPI payment deep-link."
    ),
)
def ocr_grocery_list(
    payload: HandwrittenGroceryOcrRequest,
    user: User = Depends(require_permission("orders:create")),
    db: Session = Depends(get_db),
):
    service = WhatsAppOrderingService(db=db)
    result = service.process_grocery_image_order(
        image_base64=payload.image_base64,
        mime_type=payload.mime_type,
        from_phone=payload.recipient_phone,
        sender_name=payload.sender_name,
        auto_create_order=payload.auto_create_order,
        store_id=payload.store_id or user.store_id,
        tenant_id=user.tenant_id,
    )
    return result


@router.post(
    "/ocr-grocery-list/upload",
    response_model=HandwrittenGroceryOcrResponse,
    summary="Handwritten Grocery List OCR (File Upload)",
    description="Direct image file upload (JPEG/PNG/WebP) for handwritten grocery list scanning.",
)
async def ocr_grocery_list_upload(
    file: UploadFile = File(...),
    recipient_phone: Optional[str] = Query(default=None),
    auto_create_order: bool = Query(default=True),
    store_id: Optional[int] = Query(default=None),
    user: User = Depends(require_permission("orders:create")),
    db: Session = Depends(get_db),
):
    file_bytes = await file.read()
    b64_str = base64.b64encode(file_bytes).decode("ascii")
    mime = file.content_type or "image/jpeg"

    service = WhatsAppOrderingService(db=db)
    result = service.process_grocery_image_order(
        image_base64=b64_str,
        mime_type=mime,
        from_phone=recipient_phone,
        auto_create_order=auto_create_order,
        store_id=store_id or user.store_id,
        tenant_id=user.tenant_id,
    )
    return result


# ==============================================================================
# 4. AI FEATURE 2: 24/7 WHATSAPP CONVERSATIONAL ORDERING BOT
# ==============================================================================

@router.post(
    "/conversational-order",
    response_model=WhatsAppChatOrderResponse,
    summary="Simulate WhatsApp Conversational Grocery Order",
    description=(
        "Simulates a customer sending a WhatsApp message in Marathi/Hindi/English "
        "(e.g. '२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल, अर्धा किलो साखर घरी पाठवा'). "
        "Extracts items, checks stock, creates order, generates UPI payment link, and returns reply."
    ),
)
def conversational_order(
    payload: WhatsAppChatOrderRequest,
    user: User = Depends(require_permission("orders:create")),
    db: Session = Depends(get_db),
):
    service = WhatsAppOrderingService(db=db)
    result = service.process_inbound_message(
        from_phone=payload.phone,
        message_body=payload.message,
        sender_name=payload.sender_name,
        tenant_id=user.tenant_id,
        store_id=payload.store_id or user.store_id,
    )
    return WhatsAppChatOrderResponse(
        status=result.get("status", "success"),
        intent=result.get("intent", "order_created"),
        order_id=result.get("order_id"),
        order_number=result.get("order_number"),
        total_amount=result.get("total_amount"),
        upi_link=result.get("upi_link"),
        reply=result.get("reply", ""),
    )


# ==============================================================================
# 5. AI FEATURE 3: SMART KHATA (उधारी) RECOVERY AI AGENT
# ==============================================================================

@router.get(
    "/khata/pending",
    response_model=List[KhataPendingCustomerItem],
    summary="List Customers with Pending Khata Balance",
    description="Lists all customers with outstanding credit balance exceeding threshold along with recovery status.",
)
def list_pending_khata_customers(
    min_balance: Optional[float] = Query(default=None, description="Minimum credit balance threshold"),
    store_id: Optional[int] = Query(default=None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    service = SmartKhataService(db=db, tenant_id=user.tenant_id, store_id=store_id or user.store_id)
    return service.get_pending_khata_customers(min_balance=min_balance)


@router.post(
    "/khata/send-reminder/{customer_id}",
    summary="Send AI Khata Balance Reminder",
    description="Sends a polite, personalized WhatsApp reminder with dynamic UPI link to a specific customer.",
)
def send_khata_reminder_endpoint(
    customer_id: int,
    payload: Optional[KhataReminderRequest] = None,
    user: User = Depends(require_permission("customers:create")),
    db: Session = Depends(get_db),
):
    service = SmartKhataService(db=db, tenant_id=user.tenant_id, store_id=user.store_id)
    custom_note = payload.custom_note if payload else None
    return service.send_khata_reminder(customer_id=customer_id, custom_note=custom_note)


@router.post(
    "/khata/broadcast-reminders",
    summary="Broadcast AI Khata Reminders",
    description="Queues automated smart WhatsApp reminders to all overdue customers meeting the balance threshold.",
)
def broadcast_khata_reminders_endpoint(
    payload: Optional[KhataReminderBroadcastRequest] = None,
    user: User = Depends(require_permission("customers:create")),
    db: Session = Depends(get_db),
):
    min_bal = payload.min_balance if payload else 100.0
    st_id = (payload.store_id if payload else None) or user.store_id

    task = broadcast_khata_reminders_task.delay(
        tenant_id=user.tenant_id,
        min_balance=min_bal,
        store_id=st_id,
    )
    return {
        "message": "AI Khata reminders broadcast queued",
        "task_id": task.id,
        "min_balance": min_bal,
    }


@router.post(
    "/khata/process-reply",
    summary="Process Customer's Khata WhatsApp Reply",
    description="Analyzes customer's reply using AI intent classification (promise to pay, date, dispute, paid) and schedules follow-up.",
)
def process_khata_reply_endpoint(
    payload: KhataProcessReplyRequest,
    user: User = Depends(require_permission("customers:create")),
    db: Session = Depends(get_db),
):
    service = SmartKhataService(db=db, tenant_id=user.tenant_id, store_id=user.store_id)
    return service.process_customer_khata_reply(
        customer_id=payload.customer_id,
        reply_text=payload.reply_message,
    )


@router.get(
    "/khata/followups",
    response_model=KhataFollowupListResponse,
    summary="List Khata Recovery Followups",
    description="Lists all reminder and promise-to-pay followup history.",
)
def list_khata_followups(
    status: Optional[str] = Query(default=None, description="Filter: reminder_sent, promised, paid, disputed"),
    customer_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    query = db.query(KhataFollowup).filter(KhataFollowup.tenant_id == user.tenant_id)
    if status:
        query = query.filter(KhataFollowup.status == status.lower())
    if customer_id:
        query = query.filter(KhataFollowup.customer_id == customer_id)

    total = query.count()
    items = (
        query.order_by(KhataFollowup.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    results = []
    for it in items:
        cust = db.query(Customer).filter(Customer.id == it.customer_id).first()
        results.append(
            KhataFollowupResponse(
                id=it.id,
                tenant_id=it.tenant_id,
                store_id=it.store_id,
                customer_id=it.customer_id,
                customer_name=cust.name if cust else None,
                phone=cust.phone if cust else None,
                outstanding_amount=float(it.outstanding_amount),
                reminder_sent_at=it.reminder_sent_at,
                reminder_message=it.reminder_message,
                customer_reply=it.customer_reply,
                detected_intent=it.detected_intent,
                promised_date=it.promised_date,
                status=it.status,
                notes=it.notes,
            )
        )

    return KhataFollowupListResponse(items=results, total=total)


# ==============================================================================
# 6. DELIVERY AUDIT LOGS
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
# 7. META CLOUD API WEBHOOKS
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
