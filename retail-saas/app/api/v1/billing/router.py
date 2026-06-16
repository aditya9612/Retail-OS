from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.order import InvoiceResponse, OrderResponse
from app.services.billing_service import BillingService
from app.tasks.invoice_tasks import generate_invoice_pdf_task

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/invoices/{order_id}", response_model=InvoiceResponse, status_code=201)
def create_invoice(
    order_id: int,
    same_state: bool = True,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).create_invoice(user.tenant_id, order_id, same_state)


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_invoice(user.tenant_id, invoice_id)


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    pdf_bytes = BillingService(db).generate_pdf(user.tenant_id, invoice_id)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post("/invoices/{invoice_id}/generate-async")
def generate_invoice_async(
    invoice_id: int,
    user: User = Depends(require_permission("billing:write")),
):
    task = generate_invoice_pdf_task.delay(user.tenant_id, invoice_id)
    return {"task_id": task.id}


@router.post("/orders/{order_id}/return", response_model=OrderResponse)
def process_return(
    order_id: int,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).process_return(user.tenant_id, order_id)


@router.post("/orders/{order_id}/refund", response_model=OrderResponse)
def process_refund(
    order_id: int,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).process_refund(user.tenant_id, order_id)
