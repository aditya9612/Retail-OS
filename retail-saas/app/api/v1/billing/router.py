from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import CreditNoteResponse, RefundCreate, RefundResponse
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


@router.get("/invoices", response_model=list[InvoiceResponse])
def search_invoices(
    invoice_number: Optional[str] = Query(default=None),
    customer_name: Optional[str] = Query(default=None),
    mobile: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).search_invoices(
        user.tenant_id, invoice_number, customer_name, mobile, date_from, date_to
    )


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


@router.post("/invoices/{invoice_id}/reprint", response_model=InvoiceResponse)
def reprint_invoice(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).reprint_invoice(user.tenant_id, invoice_id)


@router.post("/orders/{order_id}/return", response_model=OrderResponse)
def process_return(
    order_id: int,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).process_return(user.tenant_id, order_id)


@router.post("/refunds", response_model=RefundResponse, status_code=201)
def create_refund(
    payload: RefundCreate,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).create_refund(
        user.tenant_id,
        payload.invoice_id,
        payload.refund_amount,
        payload.refund_method,
        payload.reason,
    )


@router.get("/refunds", response_model=list[RefundResponse])
def list_refunds(
    invoice_id: Optional[int] = Query(default=None),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).list_refunds(user.tenant_id, invoice_id)


@router.get("/refunds/{refund_id}", response_model=RefundResponse)
def get_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_refund(user.tenant_id, refund_id)


@router.post("/refunds/{refund_id}/approve", response_model=RefundResponse)
def approve_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    return BillingService(db).approve_refund(user.tenant_id, refund_id, user.id)


@router.post("/refunds/{refund_id}/reject", response_model=RefundResponse)
def reject_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    return BillingService(db).reject_refund(user.tenant_id, refund_id)


@router.get("/credit-notes", response_model=list[CreditNoteResponse])
def list_credit_notes(
    invoice_id: Optional[int] = Query(default=None),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).list_credit_notes(user.tenant_id, invoice_id)


@router.get("/credit-notes/{credit_note_id}", response_model=CreditNoteResponse)
def get_credit_note(
    credit_note_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_credit_note(user.tenant_id, credit_note_id)