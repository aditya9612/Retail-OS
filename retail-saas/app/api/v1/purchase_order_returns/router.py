from datetime import date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.purchase_order_return import (
    PurchaseOrderReturnCreate,
    PurchaseOrderReturnRejectRequest,
    PurchaseOrderReturnResponse,
    PurchaseOrderReturnStatsResponse,
    PurchaseOrderReturnStatusUpdate,
    PurchaseOrderReturnUpdate,
)
from app.services.purchase_order_return_service import (
    PurchaseOrderReturnService,
)


router = APIRouter(
    prefix="/purchase-order-returns",
    tags=["purchase-order-returns"],
)


@router.post(
    "",
    response_model=PurchaseOrderReturnResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
)
def create_purchase_order_return(
    data: PurchaseOrderReturnCreate,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).create_return(
        tenant_id=user.tenant_id,
        data=data,
        user_id=user.id,
    )


@router.get(
    "",
    response_model=list[PurchaseOrderReturnResponse],
)
def list_purchase_order_returns(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    purchase_order_id: Optional[int] = Query(default=None, description="Filter by purchase order ID"),
    supplier_id: Optional[int] = Query(default=None, description="Filter by vendor / supplier ID"),
    store_id: Optional[int] = Query(default=None, description="Filter by store ID"),
    warehouse_id: Optional[int] = Query(default=None, description="Filter by warehouse ID"),
    status: Optional[str] = Query(default=None, description="Filter by status (requested, approved, rejected, completed)"),
    from_date: Optional[date] = Query(default=None, description="Filter from creation date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(default=None, description="Filter to creation date (YYYY-MM-DD)"),
    search: Optional[str] = Query(default=None, description="Search by return number, debit note, reason, or PO number"),
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    service = PurchaseOrderReturnService(db)
    items = service.list_returns(
        tenant_id=user.tenant_id,
        page=page,
        page_size=page_size,
        purchase_order_id=purchase_order_id,
        supplier_id=supplier_id,
        store_id=store_id,
        warehouse_id=warehouse_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        search=search,
    )
    total_count = service.count_returns(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        supplier_id=supplier_id,
        store_id=store_id,
        warehouse_id=warehouse_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        search=search,
    )
    total_pages = (total_count + page_size - 1) // page_size if page_size else 1

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str(total_pages)

    return items


@router.get(
    "/stats",
    response_model=PurchaseOrderReturnStatsResponse,
    summary="Get vendor returns dashboard metrics and KPIs",
)
def get_purchase_order_returns_stats(
    store_id: Optional[int] = Query(None, gt=0, description="Filter return stats by store ID"),
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(db).get_stats(tenant_id=user.tenant_id, store_id=store_id)


@router.get(
    "/by-number/{return_number}",
    response_model=PurchaseOrderReturnResponse,
    summary="Lookup purchase order return by Return Number or Debit Note Number",
)
def get_purchase_order_return_by_number(
    return_number: str,
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(db).get_by_number(
        tenant_id=user.tenant_id,
        return_number=return_number,
    )


@router.get(
    "/{return_id}",
    response_model=PurchaseOrderReturnResponse,
)
def get_purchase_order_return(
    return_id: int,
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).get_return(
        tenant_id=user.tenant_id,
        return_id=return_id,
    )


@router.get(
    "/{return_id}/pdf",
    summary="Download or Preview Debit Note / Vendor Return Slip (PDF, Excel, CSV)",
    description=(
        "Exports a formal vendor Debit Note / Return Slip in the requested format: "
        "'pdf' (branded A4 document), 'excel' (.xlsx spreadsheet), or 'csv' (comma-separated). "
        "Preview mode is supported for PDF."
    ),
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}, "description": "Visual document PNG preview for Swagger UI / browser"},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "text/csv": {},
            },
            "description": "Rendered Debit Note document stream in requested format.",
        }
    },
)
def get_purchase_order_return_pdf(
    return_id: int,
    format: Literal["pdf", "excel", "csv"] = Query(
        default="pdf",
        description="Download format: 'pdf' (A4 document), 'excel' (.xlsx), or 'csv'",
    ),
    mode: Literal["download", "preview"] = Query(
        default="download",
        description="Display mode: 'download' or 'preview' (preview only applies to PDF)",
    ),
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    service = PurchaseOrderReturnService(db)
    por = service.get_return(tenant_id=user.tenant_id, return_id=return_id)

    if format == "excel":
        content_bytes = service.generate_excel(tenant_id=user.tenant_id, return_id=return_id)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"DebitNote-{por.return_number}.xlsx"
        disposition = "attachment"
    elif format == "csv":
        content_bytes = service.generate_csv(tenant_id=user.tenant_id, return_id=return_id)
        media_type = "text/csv"
        filename = f"DebitNote-{por.return_number}.csv"
        disposition = "attachment"
    else:
        content_bytes = service.generate_pdf(tenant_id=user.tenant_id, return_id=return_id)
        return render_pdf_or_preview(
            pdf_content=content_bytes,
            filename_base=f"DebitNote-{por.return_number}",
            mode=mode,
        )

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename={filename}"
        },
    )


@router.patch(
    "/{return_id}",
    response_model=PurchaseOrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_purchase_order_return(
    return_id: int,
    data: PurchaseOrderReturnUpdate,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).update_return(
        tenant_id=user.tenant_id,
        return_id=return_id,
        data=data,
    )


@router.patch(
    "/{return_id}/status",
    response_model=PurchaseOrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_purchase_order_return_status(
    return_id: int,
    data: PurchaseOrderReturnStatusUpdate,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).update_status(
        tenant_id=user.tenant_id,
        return_id=return_id,
        data=data,
        user_id=user.id,
    )


@router.post(
    "/{return_id}/approve",
    response_model=PurchaseOrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
)
def approve_purchase_order_return(
    return_id: int,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).approve_return(
        tenant_id=user.tenant_id,
        return_id=return_id,
        user_id=user.id,
    )


@router.post(
    "/{return_id}/reject",
    response_model=PurchaseOrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
)
def reject_purchase_order_return(
    return_id: int,
    data: Optional[PurchaseOrderReturnRejectRequest] = None,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).reject_return(
        tenant_id=user.tenant_id,
        return_id=return_id,
        data=data,
        user_id=user.id,
    )


@router.post(
    "/{return_id}/complete",
    response_model=PurchaseOrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
)
def complete_purchase_order_return(
    return_id: int,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).complete_return(
        tenant_id=user.tenant_id,
        return_id=return_id,
    )