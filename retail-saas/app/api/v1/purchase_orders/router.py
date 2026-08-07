from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
    PurchaseOrderReceive,
    PurchaseOrderStatusUpdate, 
)

from app.services.purchase_order_service import PurchaseOrderService

router = APIRouter(
    prefix="/purchase-orders",
    tags=["purchase-orders"],
)


@router.post("", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED,)
def create_purchase_order(
    data: PurchaseOrderCreate,
    user: User = Depends(require_permission("purchase_orders:write")),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).create_purchase_order(
        tenant_id=user.tenant_id,
        data=data,
    )
    
    
@router.get("", response_model=list[PurchaseOrderResponse],)
def list_purchase_orders(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).list_purchase_orders(
        tenant_id=user.tenant_id,
        page=page,
        page_size=page_size,
    )
    
    
@router.get("/{purchase_order_id}", response_model=PurchaseOrderResponse,)
def get_purchase_order(
    purchase_order_id: int,
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).get_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
    )
    
    
@router.patch("/{purchase_order_id}", response_model=PurchaseOrderResponse,)
def update_purchase_order(
    purchase_order_id: int,
    data: PurchaseOrderUpdate,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).update_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )
    
    
@router.post("/{purchase_order_id}/receive", response_model=PurchaseOrderResponse,)
def receive_purchase_order(
    purchase_order_id: int,
    data: PurchaseOrderReceive,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).receive_purchase_order(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )
    
    
@router.patch("/{purchase_order_id}/status", response_model=PurchaseOrderResponse,)
def update_purchase_order_status(
    purchase_order_id: int,
    data: PurchaseOrderStatusUpdate,
    user: User = Depends(
        require_permission("purchase_orders:write")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderService(db).update_purchase_order_status(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        data=data,
    )