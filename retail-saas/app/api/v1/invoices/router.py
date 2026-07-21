from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import InvoiceCreate
from app.schemas.order import InvoiceResponse
from app.services.billing_service import BillingService
from app.tasks.invoice_tasks import generate_invoice_pdf_task

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("", response_model=InvoiceResponse, status_code=201)
def create_invoice(
    payload: InvoiceCreate,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).create_invoice_from_cart(user.tenant_id, user.id, payload)


@router.get("", response_model=list[InvoiceResponse])
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


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_invoice(user.tenant_id, invoice_id)


@router.get("/{invoice_id}/pdf")
def invoice_pdf(
    invoice_id: int,
    mode: str = Query(default="download", description="download or preview"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    
    invoice = BillingService(db).get_invoice(user.tenant_id, invoice_id)
    pdf_bytes = BillingService(db).generate_pdf(user.tenant_id, invoice_id)
    disposition = "inline" if mode == "preview" else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename={invoice.invoice_number}.pdf"
        }
    )


@router.post("/{invoice_id}/reprint")
def reprint_invoice(
    invoice_id: int,
    printer_type: str = Query(default="generic"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    result = BillingService(db).reprint_invoice(user.tenant_id, invoice_id)
    thermal = BillingService(db).get_thermal_payload(
        user.tenant_id, invoice_id, printer_type
    )
    return {
        "invoice": InvoiceResponse.model_validate(result["invoice"]),
        "print_payload": thermal,
    }


@router.post("/{invoice_id}/generate-async")
def generate_invoice_async(
    invoice_id: int,
    user: User = Depends(require_permission("billing:write")),
):
    task = generate_invoice_pdf_task.delay(user.tenant_id, invoice_id)
    return {"task_id": task.id}