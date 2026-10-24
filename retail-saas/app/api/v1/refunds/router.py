from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.exceptions import AppException, NotFoundException
from app.core.security import require_permission
from app.models.credit_note import CreditNote
from app.models.user import User
from app.schemas.billing import (
    RefundCreate,
    RefundReceiptPdfMode,
    RefundReceiptResponse,
    RefundRejectRequest,
    RefundResponse,
    RefundThermalMode,
    RefundThermalResponse,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.post("", response_model=RefundResponse, status_code=201)
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
        user=user,
    )


@router.get("", response_model=list[RefundResponse])
def list_refunds(
    invoice_id: Optional[int] = Query(default=None),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter refunds by store ID"),
    status: Optional[str] = Query(default=None, description="Filter by status: 'pending', 'approved', 'rejected'"),
    page: Optional[int] = Query(default=1, ge=1, description="Page number"),
    page_size: Optional[int] = Query(default=50, ge=1, le=100, description="Page size"),
    date_from: Optional[datetime] = Query(default=None, description="Filter refunds created on or after date"),
    date_to: Optional[datetime] = Query(default=None, description="Filter refunds created on or before date"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).list_refunds(
        user.tenant_id,
        invoice_id=invoice_id,
        store_id=store_id,
        status=status,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        user=user,
    )


@router.get("/pending-approval", response_model=list[RefundResponse])
def list_pending_refunds(
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter pending refunds by store ID"),
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    """
    Manager queue endpoint to retrieve all refund requests currently awaiting review and approval.
    """
    return BillingService(db).list_refunds(
        user.tenant_id,
        store_id=store_id,
        status="pending",
        user=user,
    )


@router.get("/{refund_id}", response_model=RefundResponse)
def get_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_refund(
        user.tenant_id,
        refund_id,
        user=user,
    )


@router.post("/{refund_id}/approve", response_model=RefundResponse)
def approve_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    return BillingService(db).approve_refund(
        user.tenant_id,
        refund_id,
        user.id,
        user=user,
    )


@router.post("/{refund_id}/reject", response_model=RefundResponse)
def reject_refund(
    refund_id: int,
    payload: Optional[RefundRejectRequest] = None,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    rejection_reason = payload.reason if payload else None
    return BillingService(db).reject_refund(
        user.tenant_id,
        refund_id,
        reason=rejection_reason,
        user=user,
    )


@router.get(
    "/{refund_id}/receipt",
    summary="Get Refund Receipt Voucher (Thermal Slip / 80mm ESC/POS)",
    description=(
        "Retrieves the refund payment voucher and 80mm ESC/POS thermal printer slip. "
        "Supports 'preview' (visual receipt PNG image displayed directly in Swagger UI), "
        "'view' (inline browser view with auto-print dialog), "
        "'download' (raw ESC/POS text file attachment), "
        "'pdf' (80mm formatted PDF receipt download), "
        "'html' (styled HTML receipt layout), "
        "'json' (structured JSON receipt response), or "
        "'text' (raw ESC/POS printer stream)."
    ),
    responses={
        200: {
            "model": RefundThermalResponse,
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
                    "schema": {"$ref": "#/components/schemas/RefundThermalResponse"},
                    "description": "Structured JSON receipt payload",
                },
            },
        }
    },
)
def get_refund_receipt(
    refund_id: int,
    request: Request,
    mode: RefundThermalMode = Query(
        default=RefundThermalMode.preview,
        description="Thermal receipt output mode: preview (visual image in Swagger UI), view (browser preview with print), download (ESC/POS text file), pdf (80mm PDF), html (raw HTML), json (structured JSON), text (raw ESC/POS text)",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).export_refund_receipt_thermal(
        user,
        refund_id,
        mode=mode,
        request=request,
    )


@router.get(
    "/{refund_id}/receipt/pdf",
    summary="Download or Preview Refund Receipt / Credit Note PDF",
    description=(
        "Exports the official branded Credit Note PDF document associated with this approved refund. "
        "Supports delivery modes: 'download' (attachment file download), 'preview' (inline browser display), "
        "or 'view' (inline browser preview)."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Rendered Credit Note PDF stream.",
        }
    },
)
def get_refund_receipt_pdf(
    refund_id: int,
    mode: RefundReceiptPdfMode = Query(
        default=RefundReceiptPdfMode.download,
        description="Delivery mode: 'download' (attachment file download), 'preview' (browser inline preview), or 'view' (inline view)",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    refund = BillingService(db).get_refund(user.tenant_id, refund_id, user=user)
    if refund.status != "approved":
        raise AppException(
            f"Refund is currently '{refund.status}'. Receipt PDF is only available for approved refunds."
        )

    credit_note = (
        db.query(CreditNote)
        .filter(CreditNote.refund_id == refund.id, CreditNote.tenant_id == user.tenant_id)
        .first()
    )
    if not credit_note:
        raise NotFoundException("Associated Credit Note not found for this refund")

    pdf_bytes = BillingService(db).generate_credit_note_pdf(
        user.tenant_id,
        credit_note.id,
        user=user,
    )
    mode_val = str(getattr(mode, "value", mode) or "download").lower().strip()
    return render_pdf_or_preview(
        pdf_content=pdf_bytes,
        filename_base=f"Refund-Receipt-{credit_note.credit_note_no}",
        mode=mode_val,
    )
