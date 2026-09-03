
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.store_transfer import (
    StoreTransferCreate,
    StoreTransferResponse
)
from app.services.store_transfer_service import StoreTransferService


router = APIRouter(
    prefix="/store-transfers",
    tags=["Store Transfers"]
)


@router.post(
    "",
    response_model=StoreTransferResponse,
    status_code=status.HTTP_201_CREATED
)
def create_transfer(
    data: StoreTransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return StoreTransferService.create_transfer(
            db=db,
            source_store_id=data.source_store_id,
            destination_store_id=data.destination_store_id,
            items=data.items
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.get(
    "",
    response_model=list[StoreTransferResponse]
)
def list_transfers(
    source_store_id: int | None = None,
    destination_store_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return StoreTransferService.get_transfers(
        db=db,
        source_store_id=source_store_id,
        destination_store_id=destination_store_id,
        status=status
    )


@router.get(
    "/{transfer_id}",
    response_model=StoreTransferResponse
)
def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return StoreTransferService.get_transfer(
            db,
            transfer_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )


@router.put(
    "/{transfer_id}/approve",
    response_model=StoreTransferResponse
)
def approve_transfer(
    transfer_id: int,
    approved_by: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return StoreTransferService.approve_transfer(
            db=db,
            transfer_id=transfer_id,
            approved_by=approved_by
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.put(
    "/{transfer_id}/reject",
    response_model=StoreTransferResponse
)
def reject_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return StoreTransferService.reject_transfer(
            db,
            transfer_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.put(
    "/{transfer_id}/dispatch",
    response_model=StoreTransferResponse
)
def dispatch_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return StoreTransferService.dispatch_transfer(
            db,
            transfer_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.put(
    "/{transfer_id}/receive",
    response_model=StoreTransferResponse
)
def receive_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return StoreTransferService.receive_transfer(
            db,
            transfer_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

