from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import (
    CreditNoteCreate,
    CreditNoteResponse,
    CreditNoteValidateRequest,
    CreditNoteValidateResponse,
    CreditNoteRedeemRequest,
    CreditNoteRedeemResponse,
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


@router.get(
    "/{credit_note_id}/thermal",
    summary="Get Credit Note Thermal Printer Voucher",
    description=(
        "Generates an 80mm/58mm thermal receipt voucher for cashier drawer printers. "
        "Supports 'json' (structured metadata), 'text' (raw ESC/POS ASCII lines), 'preview' (HTML view), "
        "or 'download' (attachment)."
    ),
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/plain": {},
                "text/html": {},
            },
            "description": "Credit Note thermal voucher payload in requested format.",
        }
    },
)
def get_credit_note_thermal(
    credit_note_id: int,
    mode: InvoiceThermalMode = Query(
        default=InvoiceThermalMode.preview,
        description="Delivery mode: 'preview' (HTML), 'text' (ESC/POS stream), 'json' (structured payload), or 'download'",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    data = BillingService(db).get_credit_note_thermal_receipt(
        user.tenant_id,
        credit_note_id,
        user=user,
    )

    # 1. JSON mode
    if mode == InvoiceThermalMode.json:
        resp = CreditNoteThermalResponse(
            success=True,
            message="Credit note thermal voucher generated successfully",
            credit_note_id=data["credit_note_id"],
            credit_note_no=data["credit_note_no"],
            invoice_id=data["invoice_id"],
            invoice_number=data["invoice_number"],
            refund_amount=data["refund_amount"],
            balance_amount=data["balance_amount"],
            status=data["status"],
            customer_name=data["customer_name"],
            customer_phone=data["customer_phone"],
            store_name=data["store_name"],
            valid_until=data["valid_until"],
            created_at=data["created_at"],
            thermal_text=data["thermal_text"],
        )
        return JSONResponse(content=resp.model_dump(mode="json"))

    # 2. HTML preview
    if mode in (InvoiceThermalMode.preview, InvoiceThermalMode.view, InvoiceThermalMode.html):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <title>Credit Note - {data['credit_note_no']}</title>
            <style>
                body {{ font-family: 'Courier New', monospace; background: #f3f4f6; margin: 0; padding: 20px; }}
                .receipt-container {{ width: 320px; margin: 0 auto; background: #fff; padding: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-radius: 4px; }}
                pre {{ font-size: 13px; line-height: 1.35; white-space: pre-wrap; word-break: break-all; margin: 0; }}
            </style>
        </head>
        <body>
            <div class="receipt-container">
                <pre>{data['thermal_text']}</pre>
            </div>
        </body>
        </html>
        """
        return Response(content=html_content, media_type="text/html; charset=utf-8")

    # 3. Text mode -> raw ASCII
    return Response(
        content=data["thermal_text"].encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"inline; filename=credit_note_{data['credit_note_no']}_thermal.txt",
            "X-CreditNote-Print-Type": "ESC/POS",
        },
    )
