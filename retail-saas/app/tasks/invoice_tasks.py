from app.core.database import SessionLocal
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
        )

        return {
            "status": "success",
            "invoice_id": invoice_id,
            "size": len(pdf_bytes),
        }
    finally:
        db.close()