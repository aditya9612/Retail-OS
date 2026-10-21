from datetime import date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.user import User

from app.schemas.grn import GRNResponse
from app.schemas.purchase_order import (
    PurchaseOrderApproveRequest,
    PurchaseOrderCancelRequest,
    PurchaseOrderCreate,
    PurchaseOrderDeleteResponse,
    PurchaseOrderReceive,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdate,
    PurchaseOrderStatsResponse,
    PurchaseOrderUpdate,
)

from app.services.purchase_order_service import PurchaseOrderService

router = APIRouter(
    prefix="/purchase-orders",
    tags=["Purchase Orders"],
)


@router.post(
    "",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
)
def create_purchase_order(
    data: PurchaseOrderCreate,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).create_purchase_order(
        tenant_id=user.tenant_id,
        data=data,
        user_id=user.id,
    )


@router.get(
    "",
    response_model=list[PurchaseOrderResponse],
)
def list_purchase_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status (draft, approved, partially_received, received, cancelled)"),
    supplier_id: Optional[int] = Query(None, description="Filter by supplier ID"),
    store_id: Optional[int] = Query(None, description="Filter by destination store ID"),
    warehouse_id: Optional[int] = Query(None, description="Filter by destination warehouse ID"),
    search: Optional[str] = Query(None, description="Search by PO number, invoice number, or supplier name"),
    from_date: Optional[date] = Query(None, description="Filter created on or after date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="Filter created on or before date (YYYY-MM-DD)"),
    delivery_from_date: Optional[date] = Query(None, description="Filter expected delivery on or after date"),
    delivery_to_date: Optional[date] = Query(None, description="Filter expected delivery on or before date"),
    response: Response = None,
    user: User = Depends(require_permission("purchase_orders:read")),
    db: Session = Depends(get_db),
):
    service = PurchaseOrderService(db)
    orders = service.list_purchase_orders(
        tenant_id=user.tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        supplier_id=supplier_id,
        store_id=store_id,
        warehouse_id=warehouse_id,
        search=search,
        from_date=from_date,
        to_date=to_date,
        delivery_from_date=delivery_from_date,
        delivery_to_date=delivery_to_date,
    )

    if response is not None:
        total = service.count_purchase_orders(
            tenant_id=user.tenant_id,
            status=status,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
            delivery_from_date=delivery_from_date,
            delivery_to_date=delivery_to_date,
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        response.headers["X-Total-Pages"] = str(total_pages)

    return orders


@router.get(
    "/stats",
    response_model=PurchaseOrderStatsResponse,
    summary="Get Procurement KPI Statistics",
    description="Returns aggregate counts and valuation metrics for open, approved, received, and cancelled purchase orders.",
)
def get_purchase_order_stats(
    store_id: Optional[int] = Query(None, gt=0, description="Filter PO stats by store ID"),
    user: User = Depends(require_permission("purchase_orders:read")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).get_stats(
        tenant_id=user.tenant_id,
        store_id=store_id,
    )



@router.get(
    "/{purchase_order_id}",
    response_model=PurchaseOrderResponse,
)
def get_purchase_order(
    purchase_order_id: int,
    user: User = Depends(require_permission("purchase_orders:read")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).get_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
    )


@router.get(
    "/{purchase_order_id}/grns",
    response_model=list[GRNResponse],
    summary="List Linked Goods Receipt Notes",
    description="Retrieves all Goods Receipt Notes (GRNs) created against this purchase order.",
)
def get_purchase_order_grns(
    purchase_order_id: int,
    user: User = Depends(require_permission("purchase_orders:read")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).get_linked_grns(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
    )


@router.get(
    "/{purchase_order_id}/pdf",
    summary="Download or Preview Purchase Order (PDF, Excel, CSV)",
    description=(
        "Exports an official vendor Purchase Order document. "
        "Supports 'pdf' (default, Purple Indigo theme #6D28D9), 'excel' (.xlsx formatted workbook), "
        "or 'csv' formats via the `format` query parameter. "
        "Delivery mode can be `download` (attachment) or `preview` (inline display). "
        "Requires 'purchase_orders:read' permission."
    ),
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "text/csv": {},
            },
            "description": "Rendered Purchase Order document stream in requested format.",
        }
    },
)
def get_purchase_order_pdf(
    purchase_order_id: int,
    format: Literal["pdf", "excel", "csv"] = Query(default="pdf", description="Export format: 'pdf', 'excel', or 'csv'"),
    mode: Literal["download", "preview"] = Query(default="download", description="'preview' for browser inline view, 'download' for file attachment"),
    user: User = Depends(require_permission("purchase_orders:read")),
    db: Session = Depends(get_db),
):
    po = PurchaseOrderService(db).get_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
    )

    disposition = "inline" if mode == "preview" else "attachment"

    if format == "pdf":
        file_bytes = PurchaseOrderService(db).generate_pdf(
            tenant_id=user.tenant_id,
            purchase_order_id=purchase_order_id,
        )
        media_type = "application/pdf"
        ext = "pdf"
    elif format == "excel":
        file_bytes = PurchaseOrderService(db).generate_excel(
            tenant_id=user.tenant_id,
            purchase_order_id=purchase_order_id,
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif format == "csv":
        file_bytes = PurchaseOrderService(db).generate_single_csv(
            tenant_id=user.tenant_id,
            purchase_order_id=purchase_order_id,
        )
        media_type = "text/csv"
        ext = "csv"
    else:
        raise AppException(f"Unsupported export format '{format}'. Choose from: pdf, excel, csv")

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename=PO-{po.order_number}.{ext}"
        },
    )


@router.patch(
    "/{purchase_order_id}",
    response_model=PurchaseOrderResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_purchase_order(
    purchase_order_id: int,
    data: PurchaseOrderUpdate,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).update_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )


@router.post(
    "/{purchase_order_id}/receive",
    response_model=PurchaseOrderResponse,
    dependencies=[Depends(require_operational_write)],
)
def receive_purchase_order(
    purchase_order_id: int,
    data: PurchaseOrderReceive,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).receive_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )


@router.patch(
    "/{purchase_order_id}/status",
    response_model=PurchaseOrderResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_purchase_order_status(
    purchase_order_id: int,
    data: PurchaseOrderStatusUpdate,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).update_purchase_order_status(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )


@router.post(
    "/{purchase_order_id}/approve",
    response_model=PurchaseOrderResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Approve Purchase Order",
    description="Marks a draft purchase order as approved and ready for supplier dispatch.",
)
def approve_purchase_order(
    purchase_order_id: int,
    data: PurchaseOrderApproveRequest = PurchaseOrderApproveRequest(),
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).approve_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
        user_id=user.id,
    )


@router.post(
    "/{purchase_order_id}/cancel",
    response_model=PurchaseOrderResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Cancel Purchase Order",
    description="Cancels an unreceived purchase order with a mandatory cancellation reason.",
)
def cancel_purchase_order(
    purchase_order_id: int,
    data: PurchaseOrderCancelRequest,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).cancel_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )


@router.delete(
    "/{purchase_order_id}",
    response_model=PurchaseOrderDeleteResponse,
    dependencies=[Depends(require_operational_write)],
)
def delete_purchase_order(
    purchase_order_id: int,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    result = PurchaseOrderService(db).delete_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
    )
    return {
        "success": True,
        "message": "Purchase order deleted successfully",
        "data": result,
    }