from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import CreditNoteCreate, CreditNoteResponse
from app.services.billing_service import BillingService

router = APIRouter(prefix="/credit-notes", tags=["Credit Notes"])


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
        user=user,
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
        user=user,
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
        user=user,
    )


@router.get(
    "/{credit_note_id}/pdf",
    summary="Download or Preview Credit Note PDF",
    description=(
        "Exports a branded GST Credit Note PDF document in Coral Red theme (#DC2626). "
        "Includes original invoice reference, customer details, itemized tax adjustments, "
        "grand total credited amount in numbers and Indian words, and signature block. "
        "Requires 'billing:read' permission."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Rendered Credit Note PDF stream.",
        }
    },
)
def credit_note_pdf(
    credit_note_id: int,
    mode: Literal["download", "preview"] = Query(default="download"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    credit_note = BillingService(db).get_credit_note(
        user.tenant_id,
        credit_note_id,
        user=user,
    )

    pdf_bytes = BillingService(db).generate_credit_note_pdf(
        user.tenant_id,
        credit_note_id,
        user=user,
    )

    disposition = "inline" if mode == "preview" else "attachment"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename=CN-{credit_note.credit_note_no}.pdf"
        },
    )