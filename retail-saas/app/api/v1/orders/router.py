from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.order import OrderCreate, OrderResponse, OrderUpdate, OrderTrackingResponse, OrderStatusUpdateRequest
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse])
def list_orders(
    store_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).list_orders(user.tenant_id, store_id, page, page_size)


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(
    data: OrderCreate,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).create_order(user.tenant_id, user.id, data)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_order(user.tenant_id, order_id)


@router.patch("/{order_id}", response_model=OrderResponse)
def update_order(
    order_id: int,
    data: OrderUpdate,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).update_order(user.tenant_id, order_id, data)


@router.post("/{order_id}/confirm", response_model=OrderResponse)
def confirm_order(
    order_id: int,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).confirm_order(user.tenant_id, order_id)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return OrderService(db).cancel_order(user.tenant_id, order_id)


@router.patch("/{order_id}/status", response_model=OrderResponse)
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
    user: User = Depends(require_permission("orders.view")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_order_tracking(
        user.tenant_id,
        order_id,
    )