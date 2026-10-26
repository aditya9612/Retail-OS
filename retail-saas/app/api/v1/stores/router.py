
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.store import (
    StoreCreate,
    StoreDeleteResponse,
    StoreInventorySummaryResponse,
    StoreResponse,
    StoreSetMainResponse,
    StoreStaffListResponse,
    StoreStatusResponse,
    StoreSummaryResponse,
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
    description="Store Owner sees all stores in their organization with optional filters. Store-assigned staff only sees their assigned store.",
)
def list_stores(
    include_inactive: bool = Query(
        False,
        description="Include deactivated or soft-deleted stores in the list",
    ),
    search: str | None = Query(
        None,
        description="Filter stores by name, code, or city",
    ),
    is_warehouse: bool | None = Query(
        None,
        description="Filter by warehouse location (true) or retail outlet (false)",
    ),
    user: User = Depends(
        require_permission("stores:read")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    return service.list_stores(
        tenant_id=user.tenant_id,
        store_id=user.store_id,
        include_inactive=include_inactive,
        search=search,
        is_warehouse=is_warehouse,
    )


@router.post(
    "/",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Store",
    description=(
        "Store Owner creates a new store for their organization "
        "under plan limits."
    ),
)
def create_store(
    data: StoreCreate,
    user: User = Depends(require_permission("stores:write")),
    service: StoreService = Depends(get_store_service),
):
    if user.store_id is not None:
        raise ForbiddenException(
            "Only Store Owner can create new stores"
        )

    return service.create_store(
        user.tenant_id,
        data,
    )


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Get Store Details",
    description="Retrieve details of a specific store. Inactive stores are also accessible to authorized admins/staff.",
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
        include_inactive=True,
    )


@router.patch(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Update Store Details",
    description="Update store attributes. Quota verification applies when reactivating an inactive store.",
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
    user: User = Depends(require_permission("stores:write")),
    service: StoreService = Depends(get_store_service),
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
    response_model=StoreDeleteResponse,
    summary="Delete Store",
    description="Soft-deletes a store if it has no active inventory or stock movements. Requires store owner privileges.",
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
    user: User = Depends(require_permission("stores:write")),
    service: StoreService = Depends(get_store_service),
):
    if user.store_id is not None:
        raise ForbiddenException(
            "Only Store Owner can delete stores"
        )

    service.delete_store(
        user.tenant_id,
        store_id,
    )

    return StoreDeleteResponse(
        success=True,
        message="Store deleted successfully",
        store_id=store_id,
    )


# ============================================================
# ADVANCED MULTI-STORE APIs
# ============================================================

@router.get(
    "/{store_id}/summary",
    response_model=StoreSummaryResponse,
    summary="Store KPI & Performance Snapshot",
    description="Real-time branch summary including today sales, orders count, total staff, open POS shifts, and stock alerts.",
)
def get_store_summary(
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

    return service.get_store_summary(
        user.tenant_id,
        store_id,
    )


@router.get(
    "/{store_id}/staff",
    response_model=StoreStaffListResponse,
    summary="List Store Staff",
    description="List all active and assigned employees (cashiers, managers, stock keepers) for this branch.",
)
def get_store_staff(
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

    return service.get_store_staff(
        user.tenant_id,
        store_id,
    )


@router.post(
    "/{store_id}/set-main",
    response_model=StoreSetMainResponse,
    summary="Set Primary / Main Store",
    description="Designates this store as the primary/main store and demotes previous main store atomically.",
)
def set_main_store(
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
        raise ForbiddenException("Only Store Owner can designate the main store")

    return service.set_main_store(
        user.tenant_id,
        store_id,
    )


@router.patch(
    "/{store_id}/activate",
    response_model=StoreStatusResponse,
    summary="Activate Store",
    description="Reactivates a deactivated store. Checks tenant SaaS subscription store quota.",
)
def activate_store(
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
        raise ForbiddenException("Only Store Owner can activate stores")

    return service.activate_store(
        user.tenant_id,
        store_id,
    )


@router.patch(
    "/{store_id}/deactivate",
    response_model=StoreStatusResponse,
    summary="Deactivate Store",
    description="Deactivates a store branch. Validates that it is not the main store and has no open POS shifts.",
)
def deactivate_store(
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
        raise ForbiddenException("Only Store Owner can deactivate stores")

    return service.deactivate_store(
        user.tenant_id,
        store_id,
    )


@router.get(
    "/{store_id}/inventory-summary",
    response_model=StoreInventorySummaryResponse,
    summary="Store Stock & Valuation Summary",
    description="Aggregated inventory statistics including total SKUs, total quantity, monetary stock valuation, and stock health counts.",
)
def get_store_inventory_summary(
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

    return service.get_store_inventory_summary(
        user.tenant_id,
        store_id,
    )
