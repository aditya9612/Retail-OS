from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.warehouse import (
    WarehouseCreate,
    WarehouseUpdate,
    WarehouseResponse,
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
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):

    return WarehouseService(db).list(
        tenant_id=user.tenant_id,
    )


@router.get(
    "/stats",
)
def warehouse_stats(
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):

    return WarehouseService(db).stats(
        tenant_id=user.tenant_id,
    )


@router.get(
    "/dashboard",
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
    warehouse_id: int,
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
    warehouse_id: int,
    data: WarehouseUpdate,
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


@router.delete(
    "/{warehouse_id}",
)
def delete_warehouse(
    warehouse_id: int,
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):

    return WarehouseService(db).delete(
        tenant_id=user.tenant_id,
        warehouse_id=warehouse_id,
    )