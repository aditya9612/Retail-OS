from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    try:
        return StoreTargetService.create_target(
            db=db,
            tenant_id=current_user.tenant_id,
            data=data,
        )
    except ValueError as e:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}",
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
    try:
        return StoreTargetService.get_targets(
            db=db,
            tenant_id=current_user.tenant_id,
            store_id=store_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}",
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
    try:
        return StoreTargetService.update_target(
            db=db,
            tenant_id=current_user.tenant_id,
            target_id=target_id,
            data=data,
        )
    except ValueError as e:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}",
        )