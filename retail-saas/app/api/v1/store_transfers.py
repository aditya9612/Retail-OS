from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_operational_write
from app.models.user import User
from app.schemas.store_transfer import (
    StoreTransferCreate,
    StoreTransferDiscrepancyRequest,
    StoreTransferDiscrepancyResponse,
    StoreTransferReject,
    StoreTransferResponse,
    StoreTransferStatus,
    StoreTransferSummaryResponse,
)
from app.services.store_transfer_service import StoreTransferService


router = APIRouter(
    prefix="/store-transfers",
    tags=["Store Transfers"]
)


@router.post(
    "",
    response_model=StoreTransferResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
)
def create_transfer(
    data: StoreTransferCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.create_transfer(
            db=db,
            source_store_id=data.source_store_id,
            destination_store_id=data.destination_store_id,
            items=data.items,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get(
    "",
    response_model=List[StoreTransferResponse],
)
def list_transfers(
    source_store_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter transfers by source store ID (must be > 0)",
    ),
    destination_store_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter transfers by destination store ID (must be > 0)",
    ),
    status: Optional[StoreTransferStatus] = Query(
        None,
        description="Filter transfers by status (Draft, Pending, Approved, Rejected, Dispatched, Received)",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="Number of records to skip for pagination",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records to return",
    ),
    search: Optional[str] = Query(
        None,
        description="Search transfers by transfer number",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        status_value = status.value if hasattr(status, "value") else (str(status) if status is not None else None)

        return StoreTransferService.get_transfers(
            db=db,
            tenant_id=current_user.tenant_id,
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            status=status_value,
            skip=skip,
            limit=limit,
            search=search,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get(
    "/summary",
    response_model=StoreTransferSummaryResponse,
    description="Get company-wide or store-specific store transfer analytics and summary dashboard",
)
def get_transfer_summary(
    store_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter analytics by store ID (source or destination)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.get_summary(
            db=db,
            tenant_id=current_user.tenant_id,
            store_id=store_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get(
    "/{transfer_id}",
    response_model=StoreTransferResponse,
)
def get_transfer(
    transfer_id: int = Path(
        ...,
        gt=0,
        description="Store transfer ID must be a positive integer greater than 0",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.put(
    "/{transfer_id}/approve",
    response_model=StoreTransferResponse,
    responses={
        200: {"description": "Store transfer approved successfully"},
    },
    dependencies=[Depends(require_operational_write)],
)
def approve_transfer(
    transfer_id: int = Path(
        ...,
        gt=0,
        description="Enter the ID of the store transfer you want to approve.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.approve_transfer(
            db=db,
            transfer_id=transfer_id,
            approved_by=current_user.id,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.put(
    "/{transfer_id}/reject",
    response_model=StoreTransferResponse,
    dependencies=[Depends(require_operational_write)],
)
def reject_transfer(
    transfer_id: int = Path(
        ...,
        gt=0,
        description="Store transfer ID must be a positive integer greater than 0",
    ),
    data: Optional[StoreTransferReject] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        rejection_reason = data.rejection_reason if data else None
        return StoreTransferService.reject_transfer(
            db=db,
            transfer_id=transfer_id,
            tenant_id=current_user.tenant_id,
            rejection_reason=rejection_reason,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.put(
    "/{transfer_id}/dispatch",
    response_model=StoreTransferResponse,
    dependencies=[Depends(require_operational_write)],
)
def dispatch_transfer(
    transfer_id: int = Path(
        ...,
        gt=0,
        description="Store transfer ID must be a positive integer greater than 0",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.dispatch_transfer(
            db=db,
            transfer_id=transfer_id,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.put(
    "/{transfer_id}/receive",
    response_model=StoreTransferResponse,
    dependencies=[Depends(require_operational_write)],
)
def receive_transfer(
    transfer_id: int = Path(
        ...,
        gt=0,
        description="Store transfer ID must be a positive integer greater than 0",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.receive_transfer(
            db=db,
            transfer_id=transfer_id,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.post(
    "/{transfer_id}/receive-with-discrepancy",
    response_model=StoreTransferDiscrepancyResponse,
    status_code=200,
    dependencies=[Depends(require_operational_write)],
    description="Receive an in-transit transfer with itemized quantity breakdown (good, damaged, missing)",
)
def receive_transfer_with_discrepancy(
    transfer_id: int = Path(
        ...,
        gt=0,
        description="Store transfer ID must be a positive integer greater than 0",
    ),
    data: StoreTransferDiscrepancyRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return StoreTransferService.receive_with_discrepancy(
            db=db,
            transfer_id=transfer_id,
            discrepancy_data=data,
            tenant_id=current_user.tenant_id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=str(e),
            )
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
