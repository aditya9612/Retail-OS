from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.store import (
    StoreCreate,
    StoreResponse,
    StoreUpdate,
)
from app.services.store_service import StoreService
router = APIRouter(
    prefix="/stores",
    tags=["Stores"],
)


def get_store_service(
    db: Session = Depends(get_db),
):
    return StoreService(db)


# ============================================================
# STORE APIs
# ============================================================

@router.get(
    "/",
    response_model=list[StoreResponse],
    summary="List Stores",
    description="Store Owner sees all stores in their organization. Store-assigned staff only see their assigned store.",
)
def list_stores(
    user: User = Depends(
        require_permission("stores:read")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    # Store Owner (store_id=None) sees all their stores; store-assigned staff only sees their assigned store
    return service.list_stores(
        tenant_id=user.tenant_id,
        store_id=user.store_id,
    )


@router.post(
    "/",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Store",
    description="Store Owner creates a new store for their organization under plan limits.",
)
def create_store(
    data: StoreCreate,
    user: User = Depends(
        require_permission("stores:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    if user.store_id is not None:
        raise ForbiddenException("Only Store Owner can create new stores")

    return service.create_store(
        user.tenant_id,
        data,
    )
@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Get Store Details",
)
def get_store(
    store_id: Annotated[
        int,
        Path(
            gt=0,
            le=999999,
            description="Store ID must be a positive integer up to 999999",
        ),
    ],
    user: User = Depends(
        require_permission("stores:read")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    if user.store_id is not None and user.store_id != store_id:
        raise ForbiddenException("Access denied to this store")

    return service.get_store(
        user.tenant_id,
        store_id,
    )

@router.patch(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Update Store Details",
)
def update_store(
    store_id: Annotated[
        int,
        Path(
            gt=0,
            le=999999,
            description="Store ID must be a positive integer up to 999999",
        ),
    ],
    data: StoreUpdate,
    user: User = Depends(
        require_permission("stores:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    if user.store_id is not None and user.store_id != store_id:
        raise ForbiddenException("Access denied to this store")

    return service.update_store(
        user.tenant_id,
        store_id,
        data,
    )


@router.delete(
    "/{store_id}",
    summary="Delete Store",
)
def delete_store(
    store_id: Annotated[
        int,
        Path(
            gt=0,
            le=999999,
            description="Store ID must be a positive integer up to 999999",
        ),
    ],
    user: User = Depends(
        require_permission("stores:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    if user.store_id is not None:
        raise ForbiddenException("Only Store Owner can delete stores")

    service.delete_store(
        user.tenant_id,
        store_id,
    )

    return {
        "message": "Store deleted successfully"
    }
