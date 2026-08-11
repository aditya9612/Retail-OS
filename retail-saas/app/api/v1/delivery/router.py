from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.delivery import (
    DeliveryResponse,
    DeliveryStatusUpdate,
)
from app.services.delivery_service import DeliveryService

router = APIRouter(
    prefix="/delivery",
    tags=["delivery"],
)


@router.get("", response_model=list[DeliveryResponse],)
def list_deliveries(
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    return DeliveryService(db).list_deliveries(
        tenant_id=user.tenant_id,
    )


@router.get("/{delivery_id}", response_model=DeliveryResponse,)
def get_delivery(
    delivery_id: int,
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    return DeliveryService(db).get_delivery(
        tenant_id=user.tenant_id,
        delivery_id=delivery_id,
    )


@router.patch("/{delivery_id}/status", response_model=DeliveryResponse,)
def update_delivery_status(
    delivery_id: int,
    data: DeliveryStatusUpdate,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    return DeliveryService(db).update_status(
        tenant_id=user.tenant_id,
        delivery_id=delivery_id,
        status=data.status,
    )