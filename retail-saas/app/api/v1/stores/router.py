from typing import Optional
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Path, status
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
from app.schemas.user import (
    UserCreate,
    UserResponse,
)
from app.services.store_service import StoreService
from app.services.user_service import UserService
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

# ============================================================
# ROLE-BASED STORE USER APIs (PER STORE)
# ============================================================

@router.get(
    "/{store_id}/users",
    response_model=list[UserResponse],
    summary="List Store Users",
    description="List all role-based users assigned to a specific store.",
)
def list_store_users(
    store_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    user: User = Depends(
        require_permission("users:read")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
    db: Session = Depends(get_db),
):
    # Verify store belongs to caller's tenant
    service.get_store(user.tenant_id, store_id)

    if user.store_id is not None and user.store_id != store_id:
        raise ForbiddenException("Access denied to users of this store")

    skip = (page - 1) * page_size
    return UserService(db).list_users(
        tenant_id=user.tenant_id,
        skip=skip,
        limit=page_size,
        include_inactive=include_inactive,
        store_id=store_id,
    )


@router.post(
    "/{store_id}/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Store User",
    description="Store Owner creates a role-based user for a specific store.",
)
def create_store_user(
    store_id: Annotated[
    int,
    Path(
        gt=0,
        le=999999,
        description="Store ID must be a positive integer up to 999999",
        ),
    ],
    data: UserCreate,
    user: User = Depends(
        require_permission("users:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
    db: Session = Depends(get_db),
):
    # Verify store belongs to caller's tenant
    service.get_store(user.tenant_id, store_id)

    if user.store_id is not None and user.store_id != store_id:
        raise ForbiddenException("You can only create users for your assigned store")

    # Force store_id to match the path store_id
    data.store_id = store_id

    return UserService(db).create_user(
        tenant_id=user.tenant_id,
        data=data,
        current_user_store_id=user.store_id,
    )