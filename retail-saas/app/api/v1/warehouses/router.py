from typing import Optional
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.warehouse import (
    WarehouseCreate,
    WarehouseUpdate,
    WarehouseResponse,
    WarehouseDeleteResponse,
    WarehouseDashboardResponse,
    WarehouseStatusUpdate,
    WarehouseStockResponse,
    WarehouseTransfersResponse,
)
from app.services.warehouse_service import WarehouseService


router = APIRouter(
    prefix="/warehouses",
    tags=["warehouses"],
)


@router.post(
    "",
    response_model=WarehouseResponse,
    status_code=201,
)
def create_warehouse(
    data: WarehouseCreate,
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).create(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.get(
    "",
    response_model=list[WarehouseResponse],
)
def list_warehouses(
    search: Optional[str] = Query(
        default=None,
        description="Search warehouse by name or code",
    ),
    is_active: Optional[bool] = Query(
        default=None,
        description="Filter by active status",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter by linked store ID",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number",
    ),
    page_size: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Items per page",
    ),
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).list(
        tenant_id=user.tenant_id,
        search=search,
        is_active=is_active,
        store_id=store_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/dashboard",
    response_model=WarehouseDashboardResponse,
)
def warehouse_dashboard(
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).dashboard(
        tenant_id=user.tenant_id,
    )


@router.get(
    "/{warehouse_id}",
    response_model=WarehouseResponse,
)
def get_warehouse(
    warehouse_id: int = Path(
        ...,
        gt=0,
        description="Warehouse ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).get(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
    )


@router.patch(
    "/{warehouse_id}",
    response_model=WarehouseResponse,
)
def update_warehouse(
    data: WarehouseUpdate,
    warehouse_id: int = Path(
        ...,
        gt=0,
        description="Warehouse ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).update(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
        data=data,
    )


@router.patch(
    "/{warehouse_id}/status",
    response_model=WarehouseResponse,
)
def update_warehouse_status(
    data: WarehouseStatusUpdate,
    warehouse_id: int = Path(
        ...,
        gt=0,
        description="Warehouse ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).update_status(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
        is_active=data.is_active,
    )


@router.get(
    "/{warehouse_id}/stock",
    response_model=WarehouseStockResponse,
)
def get_warehouse_stock(
    warehouse_id: int = Path(
        ...,
        gt=0,
        description="Warehouse ID must be a positive integer",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Search stock by product name or SKU",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number",
    ),
    page_size: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Items per page",
    ),
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).get_stock(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{warehouse_id}/transfers",
    response_model=WarehouseTransfersResponse,
)
def get_warehouse_transfers(
    warehouse_id: int = Path(
        ...,
        gt=0,
        description="Warehouse ID must be a positive integer",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum transfers to return",
    ),
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).get_transfers(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
        limit=limit,
    )


@router.delete(
    "/{warehouse_id}",
    response_model=WarehouseDeleteResponse,
)
def delete_warehouse(
    warehouse_id: int = Path(
        ...,
        gt=0,
        description="Warehouse ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):
    return WarehouseService(db).delete(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
    )