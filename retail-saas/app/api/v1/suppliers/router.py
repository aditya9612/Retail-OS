from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.supplier import (
    SupplierCreate,
    SupplierResponse,
    SupplierStatsResponse,
    SupplierStatusUpdate,
    SupplierUpdate,
    SupplierPurchaseHistoryResponse,
)

from app.services.supplier_service import SupplierService


router = APIRouter(
    prefix="/suppliers",
    tags=["suppliers"],
)

@router.post(
    "",
    response_model=SupplierResponse,
    status_code=201,
)
def create_supplier(
    data: SupplierCreate,
    user: User = Depends(
        require_permission("suppliers:write")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).create_supplier(
        user.tenant_id,
        data,
    )

@router.get(
    "",
    response_model=list[SupplierResponse],
)
def list_suppliers(
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).list_suppliers(
        user.tenant_id
    )


@router.get(
    "/search",
    response_model=list[SupplierResponse],
)
def search_suppliers(
    search: str = Query(
        ...,
        min_length=1,
        max_length=255,
        description="Search supplier by name",
    ),
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).search_suppliers(
        user.tenant_id,
        search,
    )


@router.get(
    "/stats",
    response_model=SupplierStatsResponse,
)
def supplier_stats(
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).supplier_stats(
        user.tenant_id
    )


@router.get(
    "/{supplier_id}/purchase-history",
    response_model=SupplierPurchaseHistoryResponse,
)
def get_supplier_purchase_history(
    supplier_id: int = Path(
        ...,
        gt=0,
        description="Supplier ID must be greater than zero",
    ),
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).get_purchase_history(
        user.tenant_id,
        supplier_id,
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def get_supplier(
    supplier_id: int = Path(
        ...,
        gt=0,
        description="Supplier ID must be greater than zero",
    ),
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).get_supplier(
        user.tenant_id,
        supplier_id,
    )


@router.patch(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def update_supplier(
    supplier_id: int = Path(
        ...,
        gt=0,
        description="Supplier ID must be greater than zero",
    ),
    data: SupplierUpdate = ...,
    user: User = Depends(
        require_permission("suppliers:write")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).update_supplier(
        user.tenant_id,
        supplier_id,
        data,
    )


@router.patch(
    "/{supplier_id}/status",
    response_model=SupplierResponse,
)
def update_supplier_status(
    supplier_id: int = Path(
        ...,
        gt=0,
        description="Supplier ID must be greater than zero",
    ),
    data: SupplierStatusUpdate = ...,
    user: User = Depends(
        require_permission("suppliers:write")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).update_supplier_status(
        user.tenant_id,
        supplier_id,
        data.is_active,
    )