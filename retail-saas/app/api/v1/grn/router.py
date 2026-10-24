from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import HTMLResponse

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.grn import (
    GRNCreate,
    GRNDeleteResponse,
    GRNHistoryResponse,
    GRNPrintResponse,
    GRNQualityCheckRequest,
    GRNRejectRequest,
    GRNResponse,
    GRNStatsResponse,
)
from app.services.grn_service import GRNService


router = APIRouter(
    prefix="/grn",
    tags=["grn"],
)


@router.post(
    "",
    response_model=GRNResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
)
def create_grn(
    data: GRNCreate,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).create(
        tenant_id=user.tenant_id,
        data=data,
        user_id=user.id,
    )


@router.get(
    "",
    response_model=list[GRNResponse],
)
def list_grn(
    purchase_order_id: Optional[int] = Query(None, description="Filter by purchase order ID"),
    warehouse_id: Optional[int] = Query(None, description="Filter by warehouse ID"),
    store_id: Optional[int] = Query(None, description="Filter by store ID"),
    supplier_id: Optional[int] = Query(None, description="Filter by supplier ID"),
    status: Optional[str] = Query(None, description="Filter by GRN status (pending, received, rejected)"),
    search: Optional[str] = Query(None, description="Search by GRN number, invoice, PO number, or remarks"),
    from_date: Optional[date] = Query(None, description="Filter from creation date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Filter to creation date (YYYY-MM-DD)"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=500, description="Items per page"),
    skip: Optional[int] = Query(None, ge=0, description="Skip items"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Limit items"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).list(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        warehouse_id=warehouse_id,
        store_id=store_id,
        supplier_id=supplier_id,
        status=status,
        search=search,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/stats",
    response_model=GRNStatsResponse,
)
def grn_stats(
    store_id: Optional[int] = Query(None, gt=0, description="Filter GRN stats by store ID"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).stats(tenant_id=user.tenant_id, store_id=store_id)


@router.get(
    "/by-number/{grn_number}",
    response_model=GRNResponse,
)
def get_grn_by_number(
    grn_number: str,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).get_by_number(
        tenant_id=user.tenant_id,
        grn_number=grn_number,
    )


@router.get(
    "/export",
)
def export_grn(
    from_date: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    csv_content = GRNService(db).export_csv(
        tenant_id=user.tenant_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
    )
    filename = f"grn_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/{grn_id}",
    response_model=GRNResponse,
)
def get_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).get(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.post(
    "/{grn_id}/quality-check",
    response_model=GRNResponse,
    dependencies=[Depends(require_operational_write)],
)
def quality_check_grn(
    grn_id: int,
    data: GRNQualityCheckRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).quality_check(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
        data=data,
    )


@router.post(
    "/{grn_id}/receive",
    response_model=GRNResponse,
    dependencies=[Depends(require_operational_write)],
)
def receive_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).receive(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
        user_id=user.id,
    )


@router.post(
    "/{grn_id}/reject",
    response_model=GRNResponse,
    dependencies=[Depends(require_operational_write)],
)
def reject_grn(
    grn_id: int,
    data: Optional[GRNRejectRequest] = None,
    reason: Optional[str] = Query(None, description="Optional rejection reason in query"),
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    rejection_reason = (data.reason if data and data.reason else None) or reason or "Shipment rejected during receipt"
    return GRNService(db).reject(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
        reason=rejection_reason,
        user_id=user.id,
    )


@router.delete(
    "/{grn_id}",
    response_model=GRNDeleteResponse,
    dependencies=[Depends(require_operational_write)],
)
def delete_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).delete(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.get(
    "/{grn_id}/history",
    response_model=GRNHistoryResponse,
)
def grn_history(
    grn_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).history(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.get(
    "/{grn_id}/print",
    summary="Download or Preview Goods Receipt Note (GRN) PDF",
    description="Rendered Goods Receipt Note (GRN) printable PDF document. Delivery mode can be `download` (attachment) or `preview` (inline).",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Rendered Goods Receipt Note (GRN) printable PDF document.",
        }
    },
)
def print_grn(
    grn_id: int,
    mode: Literal["download", "preview"] = Query(default="download"),
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    service = GRNService(db)
    grn = service.get(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )
    pdf_bytes = service.generate_pdf(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )

    return render_pdf_or_preview(
        pdf_content=pdf_bytes,
        filename_base=grn.grn_number,
        mode=mode,
    )


@router.get(
    "/{grn_id}/print-slip",
    response_class=HTMLResponse,
)
def print_grn_slip(
    grn_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    html_content = GRNService(db).generate_slip_html(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )
    return HTMLResponse(content=html_content)


@router.get(
    "/{grn_id}/download-pdf",
    summary="Download or Preview GRN (PDF, Excel, CSV)",
    description=(
        "Exports Goods Received Note document. "
        "Supports 'pdf' (default), 'excel' (.xlsx formatted workbook), "
        "or 'csv' formats via the `format` query parameter. "
        "Delivery mode can be `download` (attachment) or `preview` (inline display). "
        "Requires 'inventory:read' permission."
    ),
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}, "description": "Visual document PNG preview for Swagger UI / browser"},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "text/csv": {},
            },
            "description": "Rendered Goods Received Note document stream.",
        }
    },
)
def download_grn_pdf(
    grn_id: int,
    format: Literal["pdf", "excel", "csv"] = Query(default="pdf", description="Export format: 'pdf', 'excel', or 'csv'"),
    mode: str = Query("download", description="'preview' for browser inline view, 'download' for file attachment"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    grn = GRNService(db).get(user.tenant_id, grn_id)
    disposition = "inline" if mode == "preview" else "attachment"

    if format == "pdf":
        file_bytes = GRNService(db).generate_pdf(tenant_id=user.tenant_id, grn_id=grn_id)
        return render_pdf_or_preview(
            pdf_content=file_bytes,
            filename_base=grn.grn_number,
            mode=mode,
        )
    elif format == "excel":
        file_bytes = GRNService(db).generate_excel(tenant_id=user.tenant_id, grn_id=grn_id)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif format == "csv":
        file_bytes = GRNService(db).generate_single_csv(tenant_id=user.tenant_id, grn_id=grn_id)
        media_type = "text/csv"
        ext = "csv"
    else:
        raise AppException(f"Unsupported export format '{format}'. Choose from: pdf, excel, csv")

    filename = f"{grn.grn_number}.{ext}"
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f"{disposition}; filename={filename}"},
    )

