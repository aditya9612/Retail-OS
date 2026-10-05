from typing import Optional
from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.store_target import (
    StoreTargetCreate,
    StoreTargetProgressResponse,
    StoreTargetResponse,
    StoreTargetUpdate,
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
    summary="Create Store Target",
    description="Creates a new business or sales target for a store within the organization.",
)
def create_target(
    data: StoreTargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:write")),
):
    return StoreTargetService.create_target(
        db=db,
        tenant_id=current_user.tenant_id,
        data=data,
        current_user_store_id=current_user.store_id,
    )


@router.get(
    "",
    response_model=list[StoreTargetResponse],
    status_code=status.HTTP_200_OK,
    summary="List Store Targets",
    description="Retrieves a list of store targets for the organization with optional filtering.",
)
def get_targets(
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter targets by store ID",
    ),
    status: Optional[str] = Query(
        default=None,
        description="Filter targets by status (active, inactive, completed, cancelled)",
    ),
    period: Optional[str] = Query(
        default=None,
        description="Filter targets by period (daily, weekly, monthly, quarterly, yearly)",
    ),
    target_type: Optional[str] = Query(
        default=None,
        description="Filter targets by target type (e.g. Sales, Orders)",
    ),
    skip: Optional[int] = Query(
        default=None,
        ge=0,
        description="Number of records to skip for pagination",
    ),
    limit: Optional[int] = Query(
        default=None,
        gt=0,
        le=100,
        description="Maximum number of records to return",
    ),
    page: Optional[int] = Query(
        default=None,
        gt=0,
        description="Page number (alternative to skip/limit)",
    ),
    page_size: Optional[int] = Query(
        default=None,
        gt=0,
        le=100,
        description="Page size (alternative to skip/limit)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:read")),
):
    resolved_skip = skip
    resolved_limit = limit
    if page is not None and resolved_skip is None:
        p_size = page_size or 20
        resolved_skip = (page - 1) * p_size
        resolved_limit = p_size
    elif page_size is not None and resolved_limit is None:
        resolved_limit = page_size

    return StoreTargetService.get_targets(
        db=db,
        tenant_id=current_user.tenant_id,
        store_id=store_id,
        status=status,
        period=period,
        target_type=target_type,
        skip=resolved_skip,
        limit=resolved_limit,
        current_user_store_id=current_user.store_id,
    )



@router.get(
    "/{target_id}",
    response_model=StoreTargetResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Store Target",
    description="Retrieves details of a specific store target by its ID.",
)
def get_target(
    target_id: int = Path(..., gt=0, description="The ID of the store target to retrieve"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:read")),
):
    return StoreTargetService.get_target(
        db=db,
        tenant_id=current_user.tenant_id,
        target_id=target_id,
        current_user_store_id=current_user.store_id,
    )


@router.put(
    "/{target_id}",
    response_model=StoreTargetResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Store Target",
    description="Updates an existing store target.",
)
def update_target(
    target_id: int = Path(..., gt=0, description="The ID of the store target to update"),
    data: StoreTargetUpdate = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:write")),
):
    return StoreTargetService.update_target(
        db=db,
        tenant_id=current_user.tenant_id,
        target_id=target_id,
        data=data,
        current_user_store_id=current_user.store_id,
    )


@router.patch(
    "/{target_id}",
    response_model=StoreTargetResponse,
    status_code=status.HTTP_200_OK,
    summary="Partial Update Store Target",
    description="Partially updates fields of an existing store target.",
)
def patch_target(
    target_id: int = Path(..., gt=0, description="The ID of the store target to update"),
    data: StoreTargetUpdate = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:write")),
):
    return StoreTargetService.update_target(
        db=db,
        tenant_id=current_user.tenant_id,
        target_id=target_id,
        data=data,
        current_user_store_id=current_user.store_id,
    )


@router.delete(
    "/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Store Target",
    description="Permanently deletes a store target.",
)
def delete_target(
    target_id: int = Path(..., gt=0, description="The ID of the store target to delete"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:write")),
):
    StoreTargetService.delete_target(
        db=db,
        tenant_id=current_user.tenant_id,
        target_id=target_id,
        current_user_store_id=current_user.store_id,
    )
    return None


@router.get(
    "/{target_id}/progress",
    response_model=StoreTargetProgressResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Store Target Progress",
    description="Calculates real-time achievement progress against actual sales records for this store target.",
)
def get_target_progress(
    target_id: int = Path(..., gt=0, description="The ID of the store target"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("stores:read")),
):
    return StoreTargetService.get_target_progress(
        db=db,
        tenant_id=current_user.tenant_id,
        target_id=target_id,
        current_user_store_id=current_user.store_id,
    )