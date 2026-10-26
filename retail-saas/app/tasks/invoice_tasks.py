from app.core.database import SessionLocal
from app.models.invoice import Invoice
from app.services.billing_service import BillingService
from app.tasks.celery_worker import celery_app


@celery_app.task(
    name="generate_invoice_pdf",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def generate_invoice_pdf_task(self, tenant_id: int, invoice_id: int) -> dict:
    db = SessionLocal()

    try:
        service = BillingService(db)
        pdf_bytes = service.generate_pdf(
            tenant_id,
            invoice_id,
            system_context=True,
        )

        inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id).first()
        if inv and not inv.pdf_url:
            inv.pdf_url = f"/api/v1/invoices/{invoice_id}/pdf"
            db.commit()

        return {
            "status": "success",
            "invoice_id": invoice_id,
            "size": len(pdf_bytes),
            "pdf_url": inv.pdf_url if inv else f"/api/v1/invoices/{invoice_id}/pdf",
        }
    finally:
        db.close()
