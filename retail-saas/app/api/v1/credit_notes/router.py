from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import (
    CreditNoteCreate,
    CreditNoteResponse,
    CreditNoteValidateRequest,
    CreditNoteValidateResponse,
    CreditNoteRedeemRequest,
    CreditNoteRedeemResponse,
    CreditNoteThermalMode,
    CreditNoteThermalResponse,
    InvoiceThermalMode,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/credit-notes", tags=["Credit Notes"])


@router.post("", response_model=CreditNoteResponse, status_code=201)
def create_credit_note(
    payload: CreditNoteCreate,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    """
    Creates a new Credit Note against an issued invoice with proportional GST breakdown.
    Supports refund method (store_credit, cash, upi), validity period, and custom notes.
    """
    return BillingService(db).create_credit_note(
        user.tenant_id,
        payload.invoice_id,
        payload.refund_amount,
        payload.reason,
        user.id,
        refund_method=payload.refund_method if payload.refund_method else "cash",
        valid_days=getattr(payload, "valid_days", 90) or 90,
        notes=getattr(payload, "notes", None),
        user=user,
    )


@router.get("", response_model=list[CreditNoteResponse])
def list_credit_notes(
    invoice_id: Optional[int] = Query(default=None, gt=0, description="Filter by invoice ID"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter credit notes by store ID"),
    credit_note_no: Optional[str] = Query(default=None, description="Search by credit note number"),
    status: Optional[str] = Query(default=None, description="Filter by status (issued, partially_redeemed, redeemed, expired)"),
    customer_id: Optional[int] = Query(default=None, gt=0, description="Filter by customer ID"),
    date_from: Optional[datetime] = Query(default=None, description="Filter credit notes created on or after this timestamp"),
    date_to: Optional[datetime] = Query(default=None, description="Filter credit notes created on or before this timestamp"),
    page: Optional[int] = Query(default=None, ge=1, description="Page number for pagination"),
    page_size: Optional[int] = Query(default=None, ge=1, le=100, description="Page size limit"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    """
    Lists credit notes with optional filters (store, invoice, credit_note_no, status, customer, date range, pagination).
    """
    return BillingService(db).list_credit_notes(
        user.tenant_id,
        invoice_id=invoice_id,
        store_id=store_id,
        credit_note_no=credit_note_no,
        status=status,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        user=user,
    )


@router.post(
    "/validate",
    response_model=CreditNoteValidateResponse,
    summary="Validate Credit Note at POS Checkout",
    description="Validates a Credit Note number, remaining balance, expiry, and calculates applicable deduction against a bill.",
)
def validate_credit_note(
    payload: CreditNoteValidateRequest,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).validate_credit_note(
        user.tenant_id,
        payload.credit_note_no,
        bill_amount=payload.bill_amount,
        user=user,
    )


@router.post(
    "/redeem",
    response_model=CreditNoteRedeemResponse,
    summary="Redeem Credit Note towards Bill",
    description="Redeems an amount from an active credit note, updates remaining balance, and logs a redemption audit entry.",
)
def redeem_credit_note(
    payload: CreditNoteRedeemRequest,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).redeem_credit_note(
        user.tenant_id,
        credit_note_no=payload.credit_note_no,
        amount_to_redeem=payload.amount_to_redeem,
        invoice_id=payload.invoice_id,
        order_id=payload.order_id,
        notes=payload.notes,
        user=user,
    )


@router.get(
    "/by-number/{credit_note_no}",
    response_model=CreditNoteResponse,
    summary="Lookup Credit Note by Number",
    description="Retrieves a credit note directly by its human-readable document number (e.g. CN-2026-000001). Useful for barcode scanners.",
)
def get_credit_note_by_number(
    credit_note_no: str,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_credit_note_by_number(
        user.tenant_id,
        credit_note_no,
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
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}, "description": "Visual document PNG preview for Swagger UI / browser"},
            },
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

    return render_pdf_or_preview(
        pdf_content=pdf_bytes,
        filename_base=f"CN-{credit_note.credit_note_no}",
        mode=mode,
    )


@router.get(
    "/{credit_note_id}/thermal",
    summary="Export Credit Note Thermal Slip (80mm ESC/POS)",
    description=(
        "Generates an 80mm ESC/POS thermal receipt slip for an issued credit note voucher. "
        "Supports 'preview' (visual receipt PNG image displayed directly in Swagger UI), "
        "'view' (inline browser view with auto-print dialog), "
        "'download' (raw ESC/POS text file attachment), "
        "'pdf' (80mm formatted PDF receipt download), "
        "'html' (styled HTML receipt layout), "
        "'json' (structured JSON response), or "
        "'text' (raw ESC/POS printer stream)."
    ),
    responses={
        200: {
            "model": CreditNoteThermalResponse,
            "description": "Thermal receipt preview (PNG), HTML render, PDF/Text download, or JSON payload.",
            "content": {
                "image/png": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "Visual 80mm thermal receipt PNG rendered directly in Swagger UI",
                },
                "text/html": {
                    "schema": {"type": "string"},
                    "description": "Styled 80mm thermal receipt HTML for browser preview or print",
                },
                "application/pdf": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "80mm thermal receipt PDF document",
                },
                "text/plain": {
                    "schema": {"type": "string"},
                    "description": "Raw 80mm ESC/POS thermal printer text stream",
                },
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/CreditNoteThermalResponse"},
                    "description": "Structured JSON receipt payload",
                },
            },
        }
    },
)
def get_credit_note_thermal(
    credit_note_id: int,
    request: Request,
    mode: CreditNoteThermalMode = Query(
        default=CreditNoteThermalMode.preview,
        description="Thermal receipt output mode: preview (visual image in Swagger UI), view (browser preview with print), download (ESC/POS text file), pdf (80mm PDF), html (raw HTML), json (structured JSON), text (raw ESC/POS text)",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).export_credit_note_thermal(
        user=user,
        credit_note_id=credit_note_id,
        mode=mode,
        request=request,
    )
