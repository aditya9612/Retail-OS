from typing import Optional
from app.tasks.celery_worker import celery_app
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.invoice import Invoice
from app.services.whatsapp_service import WhatsAppService


@celery_app.task(
    name="send_whatsapp_invoice",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_whatsapp_invoice_task(
    self,
    tenant_id: int,
    invoice_id: int,
    recipient_phone: Optional[str] = None,
    custom_note: Optional[str] = None,
) -> dict:
    """Asynchronously dispatches an invoice PDF and details to customer WhatsApp via Meta Cloud API."""
    db = SessionLocal()
    try:
        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .first()
        )
        if not invoice:
            logger.warning("Invoice %s not found for WhatsApp dispatch (tenant %s)", invoice_id, tenant_id)
            return {"status": "skipped", "reason": "Invoice not found"}

        service = WhatsAppService(
            db=db,
            tenant_id=tenant_id,
            store_id=invoice.store_id,
        )
        return service.send_invoice_notification(
            invoice=invoice,
            recipient_phone=recipient_phone,
            custom_note=custom_note,
        )
    finally:
        db.close()


@celery_app.task(
    name="send_order_confirmation",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_order_confirmation_task(
    self,
    phone: str,
    order_number: str,
    total: str,
    tenant_id: Optional[int] = None,
    store_id: Optional[int] = None,
    store_name: str = "Retail Store",
) -> dict:
    """Asynchronously dispatches order confirmation alert to customer WhatsApp."""
    db = SessionLocal()
    try:
        service = WhatsAppService(
            db=db,
            tenant_id=tenant_id,
            store_id=store_id,
        )
        return service.send_order_confirmation(
            phone=phone,
            order_number=order_number,
            total=total,
            store_name=store_name,
        )
    finally:
        db.close()


@celery_app.task(name="send_whatsapp_message")
def send_whatsapp_message_task(
    phone: str,
    message: str,
    tenant_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> dict:
    """Sends a general text WhatsApp message."""
    db = SessionLocal()
    try:
        service = WhatsAppService(
            db=db,
            tenant_id=tenant_id,
            store_id=store_id,
        )
        return service.send_message(phone, message)
    finally:
        db.close()


@celery_app.task(
    name="send_khata_reminder",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_khata_reminder_task(
    self,
    tenant_id: int,
    customer_id: int,
    store_id: Optional[int] = None,
    custom_note: Optional[str] = None,
) -> dict:
    """Asynchronously dispatches an AI Khata balance reminder with dynamic UPI link to a customer."""
    db = SessionLocal()
    try:
        from app.services.smart_khata_service import SmartKhataService
        service = SmartKhataService(db=db, tenant_id=tenant_id, store_id=store_id)
        return service.send_khata_reminder(customer_id=customer_id, custom_note=custom_note)
    finally:
        db.close()


@celery_app.task(
    name="broadcast_khata_reminders",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def broadcast_khata_reminders_task(
    self,
    tenant_id: int,
    min_balance: Optional[float] = None,
    store_id: Optional[int] = None,
) -> dict:
    """Asynchronously broadcasts Khata reminders to all eligible overdue customers."""
    db = SessionLocal()
    try:
        from app.services.smart_khata_service import SmartKhataService
        service = SmartKhataService(db=db, tenant_id=tenant_id, store_id=store_id)
        return service.broadcast_khata_reminders(min_balance=min_balance)
    finally:
        db.close()


@celery_app.task(
    name="process_handwritten_grocery_ocr",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def process_handwritten_grocery_ocr_task(
    self,
    tenant_id: int,
    image_base64: str,
    mime_type: str = "image/jpeg",
    from_phone: Optional[str] = None,
    sender_name: Optional[str] = None,
    auto_create_order: bool = True,
    store_id: Optional[int] = None,
) -> dict:
    """Asynchronously processes a handwritten grocery list image via Gemini Vision."""
    db = SessionLocal()
    try:
        from app.services.whatsapp_ordering_service import WhatsAppOrderingService
        service = WhatsAppOrderingService(db=db)
        return service.process_grocery_image_order(
            image_base64=image_base64,
            mime_type=mime_type,
            from_phone=from_phone,
            sender_name=sender_name,
            auto_create_order=auto_create_order,
            store_id=store_id,
            tenant_id=tenant_id,
        )
    finally:
        db.close()
