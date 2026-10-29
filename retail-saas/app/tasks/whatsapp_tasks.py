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
