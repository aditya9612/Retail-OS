from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.purchase_order_return import (
    PurchaseOrderReturnCreate,
    PurchaseOrderReturnResponse,
    PurchaseOrderReturnUpdate,
    PurchaseOrderReturnStatusUpdate,
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
    )


@router.get(
    "",
    response_model=list[PurchaseOrderReturnResponse],
)
def list_purchase_order_returns(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(
        require_permission("purchase_orders:read")
    ),
    db: Session = Depends(get_db),
):
    return PurchaseOrderReturnService(
        db
    ).list_returns(
        tenant_id=user.tenant_id,
        page=page,
        page_size=page_size,
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


@router.patch(
    "/{return_id}",
    response_model=PurchaseOrderReturnResponse,
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
    )


@router.post(
    "/{return_id}/approve",
    response_model=PurchaseOrderReturnResponse,
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
    )


@router.post(
    "/{return_id}/reject",
    response_model=PurchaseOrderReturnResponse,
)
def reject_purchase_order_return(
    return_id: int,
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
    )


@router.post(
    "/{return_id}/complete",
    response_model=PurchaseOrderReturnResponse,
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