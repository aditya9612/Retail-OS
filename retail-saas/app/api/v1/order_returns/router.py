from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.order_return import (
    OrderReturnCreate,
    OrderReturnRejectRequest,
    OrderReturnResponse,
    OrderReturnStatusUpdate,
    OrderReturnUpdate,
)
from app.services.order_return_service import OrderReturnService


router = APIRouter(
    prefix="/order-returns",
    tags=["Order Returns"],
)

@router.post(
    "",
    response_model=OrderReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_return(
    data: OrderReturnCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.create_return(
        db=db,
        data=data,
        tenant_id=current_user.tenant_id,
    )

@router.get(
    "",
    response_model=list[OrderReturnResponse],
)
def list_returns(
    skip: int = Query(
        0,
        ge=0,
        description="Number of records to skip",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum records to return",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.list_returns(
        db=db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit,
    )

@router.get(
    "/{return_id}",
    response_model=OrderReturnResponse,
)
def get_return(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.get_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
    )

@router.patch(
    "/{return_id}",
    response_model=OrderReturnResponse,
)
def update_return(
    data: OrderReturnUpdate,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.update_return(
        db=db,
        return_id=return_id,
        data=data,
        tenant_id=current_user.tenant_id,
    )

@router.patch(
    "/{return_id}/status",
    response_model=OrderReturnResponse,
)
def update_return_status(
    data: OrderReturnStatusUpdate,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.update_status(
        db=db,
        return_id=return_id,
        data=data,
        tenant_id=current_user.tenant_id,
    )

@router.post(
    "/{return_id}/approve",
    response_model=OrderReturnResponse,
)
def approve_return(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.approve_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
    )

@router.post(
    "/{return_id}/reject",
    response_model=OrderReturnResponse,
)
def reject_return(
    data: OrderReturnRejectRequest,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.reject_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
        remarks=data.remarks,
    )

@router.post(
    "/{return_id}/complete",
    response_model=OrderReturnResponse,
)
def complete_return(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.complete_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
    )