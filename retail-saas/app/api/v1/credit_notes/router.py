from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import CreditNoteCreate, CreditNoteResponse
from app.services.billing_service import BillingService

router = APIRouter(prefix="/credit-notes", tags=["credit-notes"])


@router.post("", response_model=CreditNoteResponse, status_code=201)
def create_credit_note(
    payload: CreditNoteCreate,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    return BillingService(db).create_credit_note(
        user.tenant_id,
        payload.invoice_id,
        payload.refund_amount,
        payload.reason,
        user.id,
    )


@router.get("", response_model=list[CreditNoteResponse])
def list_credit_notes(
    invoice_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).list_credit_notes(
        user.tenant_id,
        invoice_id,
    )


@router.get("/{credit_note_id}", response_model=CreditNoteResponse)
def get_credit_note(
    credit_note_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_credit_note(
        user.tenant_id,
        credit_note_id,
    )


@router.get("/{credit_note_id}/pdf")
def credit_note_pdf(
    credit_note_id: int,
    mode: Literal["download", "preview"] = Query(default="download"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    credit_note = BillingService(db).get_credit_note(
        user.tenant_id,
        credit_note_id,
    )

    pdf_bytes = BillingService(db).generate_credit_note_pdf(
        user.tenant_id,
        credit_note_id,
    )

    disposition = "inline" if mode == "preview" else "attachment"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename=CN-{credit_note.credit_note_no}.pdf"
        },
    )