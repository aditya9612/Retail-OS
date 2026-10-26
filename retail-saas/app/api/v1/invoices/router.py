from datetime import datetime
from typing import Optional, Literal

from celery.exceptions import CeleryError
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.security import is_tenant_wide_authorized, require_operational_write, require_permission
from app.models.store import Store
from app.models.user import User
from app.schemas.billing import (
    InvoiceCreate,
    InvoicePdfStatusResponse,
    InvoiceReprintRequest,
    InvoiceThermalMode,
    InvoiceThermalResponse,
    InvoiceVoidRequest,
)
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
    if user.store_id is not None and payload.store_id != user.store_id:
        raise ForbiddenException("Access denied: cannot create invoice for another store")

    if user.store_id is None:
        if not is_tenant_wide_authorized(user, db):
            raise ForbiddenException("Access denied: user has no assigned store")
        store = (
            db.query(Store)
            .filter(
                Store.id == payload.store_id,
                Store.tenant_id == user.tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )
        if not store:
            raise NotFoundException(f"Store {payload.store_id} not found")

    return BillingService(db).create_invoice_from_cart(
        user.tenant_id,
        user.id,
        payload,
        user=user,
    )


@router.get("", response_model=list[InvoiceResponse])
def search_invoices(
    invoice_number: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    customer_name: Optional[str] = Query(
        default=None,
        min_length=2,
        max_length=100,
    ),
    mobile: Optional[str] = Query(
        default=None,
        min_length=10,
        max_length=10,
        pattern=r"^\d{10}$",
    ),
    gstin: Optional[str] = Query(
        default=None,
        min_length=15,
        max_length=15,
        pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    ),
    payment_status: Optional[
        Literal["paid", "unpaid", "partial", "cancelled", "completed", "pending", "failed"]
    ] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    store_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Items per page"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    invoice_number = invoice_number.strip() if invoice_number else None
    customer_name = customer_name.strip() if customer_name else None
    mobile = mobile.strip() if mobile else None
    gstin = gstin.strip().upper() if gstin else None

    if invoice_number is not None and not invoice_number:
        raise HTTPException(
            status_code=422,
            detail="invoice_number cannot be empty",
        )

    if customer_name is not None and not customer_name:
        raise HTTPException(
            status_code=422,
            detail="customer_name cannot be empty",
        )

    if customer_name is not None and len(customer_name) < 2:
        raise HTTPException(
            status_code=422,
            detail="customer_name must contain at least 2 characters",
        )

    if mobile is not None:
        if not mobile.isdigit() or len(mobile) != 10:
            raise HTTPException(
                status_code=422,
                detail="mobile must be exactly 10 digits",
            )

    if gstin is not None:
        import re

        if not re.fullmatch(
            r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
            gstin,
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid GSTIN format",
            )

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from must be earlier than or equal to date_to",
        )

    if not any(
        [
            invoice_number,
            customer_name,
            mobile,
            gstin,
            payment_status,
            date_from,
            date_to,
            store_id,
        ]
    ):
        raise HTTPException(
            status_code=422,
            detail="At least one search parameter is required",
        )

    effective_store_id = store_id
    if user.store_id is not None:
        if store_id is not None and store_id != user.store_id:
            raise ForbiddenException("Access denied: store staff cannot query other stores' invoices")
        effective_store_id = user.store_id
    elif store_id is not None:
        store = (
            db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == user.tenant_id,
            )
            .first()
        )
        if not store:
            raise NotFoundException(f"Store {store_id} not found")

    return BillingService(db).search_invoices(
        user.tenant_id,
        invoice_number,
        customer_name,
        mobile,
        gstin,
        payment_status,
        date_from,
        date_to,
        effective_store_id,
        user=user,
        page=page,
        page_size=page_size,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_invoice(
        user.tenant_id,
        invoice_id,
        user=user,
    )


@router.get(
    "/{invoice_id}/pdf",
    summary="Download or Preview Tax Invoice / Bill PDF",
    description=(
        "Exports an authoritative, dynamically rendered PDF document for a sales transaction. "
        "Supports formal B2B/B2C Tax Invoice format (default, Corporate Navy Blue theme) or compact POS Bill / Receipt format "
        "(Emerald Green theme) via the `document_type` query parameter. Delivery mode can be `download` (attachment) or `preview` (inline). "
        "Requires 'billing:read' permission."
    ),
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}, "description": "Visual document PNG preview for Swagger UI / browser"},
            },
            "description": "Rendered PDF document download or visual PNG preview for Swagger UI.",
        }
    },
)
def invoice_pdf(
    invoice_id: int,
    mode: Literal["download", "preview"] = Query(default="download"),
    document_type: Literal["invoice", "bill"] = Query(default="invoice"),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    invoice = BillingService(db).get_invoice(
        user.tenant_id,
        invoice_id,
        user=user,
    )

    pdf_bytes = BillingService(db).generate_pdf(
        user.tenant_id,
        invoice_id,
        document_type=document_type,
        user=user,
    )

    filename_prefix = "bill_" if document_type == "bill" else ""
    return render_pdf_or_preview(
        pdf_content=pdf_bytes,
        filename_base=f"{filename_prefix}{invoice.invoice_number}",
        mode=mode,
    )


@router.get(
    "/{invoice_id}/thermal",
    summary="Export Invoice / POS Thermal Receipt Slip (80mm ESC/POS)",
    description=(
        "Generates an 80mm ESC/POS thermal receipt slip for an issued sales invoice. "
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
            "model": InvoiceThermalResponse,
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
                    "schema": {"$ref": "#/components/schemas/InvoiceThermalResponse"},
                    "description": "Structured JSON receipt payload",
                },
            },
        }
    },
)
def export_invoice_thermal(
    invoice_id: int,
    mode: InvoiceThermalMode = Query(
        default=InvoiceThermalMode.preview,
        description="Thermal receipt output mode: preview (visual image in Swagger UI), view (browser preview with print), download (ESC/POS text file), pdf (80mm PDF), html (raw HTML), json (structured JSON), text (raw ESC/POS text)",
    ),
    printer_type: Literal["generic", "epson", "tvs"] = Query(
        default="generic",
        description="Target thermal printer type",
    ),
    is_reprint: bool = Query(
        default=False,
        description="Whether to include DUPLICATE/REPRINT watermark on receipt",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).export_invoice_thermal(
        user=user,
        invoice_id=invoice_id,
        mode=mode,
        printer_type=printer_type,
        is_reprint=is_reprint,
    )


@router.post(
    "/{invoice_id}/reprint",
    summary="Reprint Invoice Thermal Receipt",
    description="Reprint an invoice thermal slip with '*** DUPLICATE / REPRINT ***' header. Supports optional 'mode' query parameter (preview, view, download, pdf, html, json, text).",
)
def reprint_invoice(
    invoice_id: int,
    data: Optional[InvoiceReprintRequest] = None,
    mode: Optional[InvoiceThermalMode] = Query(
        default=None,
        description="Optional thermal output mode: preview, view, download, pdf, html, json, text. Defaults to structured JSON reprint response if omitted.",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    printer_type = data.printer_type if data and data.printer_type else "generic"
    selected_mode = mode or (data.mode if data else None)

    if selected_mode and selected_mode != InvoiceThermalMode.json:
        return BillingService(db).export_invoice_thermal(
            user=user,
            invoice_id=invoice_id,
            mode=selected_mode,
            printer_type=printer_type,
            is_reprint=True,
        )

    result = BillingService(db).reprint_invoice(
        user.tenant_id,
        invoice_id,
        printer_type=printer_type,
        user=user,
    )

    if selected_mode == InvoiceThermalMode.json:
        return BillingService(db).export_invoice_thermal(
            user=user,
            invoice_id=invoice_id,
            mode=InvoiceThermalMode.json,
            printer_type=printer_type,
            is_reprint=True,
        )

    return {
        "invoice": InvoiceResponse.model_validate(result["invoice"]),
        "print_payload": result["print_payload"],
    }


@router.post("/{invoice_id}/generate-async")
def generate_invoice_async(
    invoice_id: int,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    BillingService(db).get_invoice(
        user.tenant_id,
        invoice_id,
        user=user,
    )

    try:
        task = generate_invoice_pdf_task.delay(
            user.tenant_id,
            invoice_id,
        )
    except CeleryError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Invoice PDF task could not be queued: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Invoice PDF task could not be queued: {exc}",
        )

    return {
        "message": "Invoice PDF generation queued successfully",
        "task_id": task.id,
        "invoice_id": invoice_id,
    }

@router.get(
    "/by-number/{invoice_number}",
    response_model=InvoiceResponse,
    summary="Lookup Invoice by Invoice Number",
    description="Retrieves a tax invoice directly by its official invoice number (useful for barcode scanning).",
)
def get_invoice_by_number(
    invoice_number: str,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_invoice_by_number(
        user.tenant_id,
        invoice_number,
        user=user,
    )


@router.get(
    "/{invoice_id}/pdf-status",
    response_model=InvoicePdfStatusResponse,
    summary="Check Invoice PDF Readiness Status",
    description="Returns the PDF generation status and URL for an invoice.",
)
def get_invoice_pdf_status(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    invoice = BillingService(db).get_invoice(
        user.tenant_id,
        invoice_id,
        user=user,
    )
    pdf_url = invoice.pdf_url or f"/api/v1/invoices/{invoice.id}/pdf"
    return InvoicePdfStatusResponse(
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        status="ready",
        pdf_url=pdf_url,
    )


@router.post(
    "/{invoice_id}/void",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Void or Cancel an Issued Tax Invoice",
    description="Voids an unpaid or counter-cancelled invoice, restores stock, and cancels payments.",
)
def void_invoice(
    invoice_id: int,
    payload: InvoiceVoidRequest = InvoiceVoidRequest(),
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).void_invoice(
        user.tenant_id,
        invoice_id,
        reason=payload.reason,
        user=user,
    )
