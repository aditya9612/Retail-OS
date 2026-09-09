from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.store_target import (
    StoreTargetCreate,
    StoreTargetUpdate,
    StoreTargetResponse,
)
from app.services.store_target_service import StoreTargetService


router = APIRouter(
    prefix="/store-targets",
    tags=["Store Targets"],
)


@router.post(
    "",
    response_model=StoreTargetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_target(
    data: StoreTargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    return StoreTargetService.create_target(
        db=db,
        tenant_id=tenant_id,
        data=data,
    )


@router.get(
    "",
    response_model=list[StoreTargetResponse],
    status_code=status.HTTP_200_OK,
)
def get_targets(
    store_id: int | None = Query(
        default=None,
        gt=0,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    return StoreTargetService.get_targets(
        db=db,
        tenant_id=tenant_id,
        store_id=store_id,
    )


@router.put(
    "/{target_id}",
    response_model=StoreTargetResponse,
    status_code=status.HTTP_200_OK,
)
def update_target(
    target_id: int,
    data: StoreTargetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    return StoreTargetService.update_target(
        db=db,
        tenant_id=tenant_id,
        target_id=target_id,
        data=data,
    )