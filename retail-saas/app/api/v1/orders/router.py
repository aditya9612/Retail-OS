from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import is_tenant_wide_authorized, require_operational_write, require_permission
from app.models.user import User
from app.schemas.order import (
    OrderAddItemsRequest,
    OrderCreate,
    OrderItemCreate,
    OrderReceiptResponse,
    OrderResponse,
    OrderStatusUpdateRequest,
    OrderStatsResponse,
    OrderTrackingResponse,
    OrderUpdate,
    POSCheckoutRequest,
    POSCheckoutResponse,
)
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse])
def list_orders(
    store_id: Optional[int] = Query(None, description="Filter by store ID"),
    status: Optional[str] = Query(None, description="Filter by order status"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    order_type: Optional[str] = Query(None, description="Filter by order type (pos, ecommerce)"),
    date_from: Optional[datetime] = Query(None, description="Filter orders created on or after this date"),
    date_to: Optional[datetime] = Query(None, description="Filter orders created on or before this date"),
    search: Optional[str] = Query(None, description="Search by order number or notes"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).list_orders(
        tenant_id=user.tenant_id,
        store_id=store_id,
        status=status,
        customer_id=customer_id,
        order_type=order_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=OrderResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def create_order(
    data: OrderCreate,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    if user.store_id is not None and data.store_id != user.store_id:
        raise ForbiddenException("Access denied: cannot create order for another store")
    if user.store_id is None and not is_tenant_wide_authorized(user, db):
        raise ForbiddenException("Access denied: user has no assigned store")
    return OrderService(db).create_order(user.tenant_id, user.id, data)


@router.post("/pos-checkout", response_model=POSCheckoutResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def pos_checkout(
    data: POSCheckoutRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).pos_checkout(user.tenant_id, user.id, data)


@router.get("/stats", response_model=OrderStatsResponse)
def get_order_stats(
    store_id: Optional[int] = Query(None, description="Filter stats by store ID"),
    date_from: Optional[datetime] = Query(None, description="Start date"),
    date_to: Optional[datetime] = Query(None, description="End date"),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_order_stats(
        tenant_id=user.tenant_id,
        store_id=store_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/export",
    summary="Export orders to Excel or CSV",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "text/csv": {},
            },
            "description": "Exported Orders data stream.",
        }
    },
)
def export_orders(
    format: str = Query("excel", description="Export format: excel or csv"),
    status: Optional[str] = Query(None, description="Filter by status"),
    order_type: Optional[str] = Query(None, description="Filter by order type"),
    store_id: Optional[int] = Query(None, description="Filter by store ID"),
    date_from: Optional[datetime] = Query(None, description="Start date"),
    date_to: Optional[datetime] = Query(None, description="End date"),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    buffer, media_type, filename = OrderService(db).export_orders(
        tenant_id=user.tenant_id,
        format=format.strip().lower(),
        store_id=store_id,
        status=status,
        order_type=order_type,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_order(user.tenant_id, order_id)


@router.patch("/{order_id}", response_model=OrderResponse, dependencies=[Depends(require_operational_write)])
def update_order(
    order_id: int,
    data: OrderUpdate,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).update_order(user.tenant_id, order_id, data)


@router.post("/{order_id}/items", response_model=OrderResponse, dependencies=[Depends(require_operational_write)])
def add_order_items(
    order_id: int,
    data: OrderAddItemsRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).add_order_items(user.tenant_id, order_id, data.items)


@router.get("/{order_id}/receipt", response_model=OrderReceiptResponse)
def get_order_receipt(
    order_id: int,
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_order_receipt(user.tenant_id, order_id)


@router.post("/{order_id}/confirm", response_model=OrderResponse, dependencies=[Depends(require_operational_write)])
def confirm_order(
    order_id: int,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).confirm_order(user.tenant_id, order_id)


@router.post("/{order_id}/cancel", response_model=OrderResponse, dependencies=[Depends(require_operational_write)])
def cancel_order(
    order_id: int,
    restore_stock: bool = Query(False, description="Restore reserved inventory back to stock upon cancellation"),
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).cancel_order(user.tenant_id, order_id, restore_stock=restore_stock)


@router.patch("/{order_id}/status", response_model=OrderResponse, dependencies=[Depends(require_operational_write)])
def update_order_status(
    order_id: int,
    data: OrderStatusUpdateRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).update_order_status(
        user.tenant_id,
        order_id,
        data.status,
        data.remarks,
    )


@router.get(
    "/{order_id}/tracking",
    response_model=list[OrderTrackingResponse],
)
def order_tracking(
    order_id: int,
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_order_tracking(
        user.tenant_id,
        order_id,
    )
