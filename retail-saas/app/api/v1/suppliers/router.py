from typing import Optional, Union
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.supplier import (
    SupplierCreate,
    SupplierDeleteResponse,
    SupplierEmptyResponse,
    SupplierProductsResponse,
    SupplierPurchaseHistoryResponse,
    SupplierResponse,
    SupplierStatusUpdate,
    SupplierSummaryResponse,
    SupplierUpdate,
)

from app.services.supplier_service import SupplierService


router = APIRouter(
    prefix="/suppliers",
    tags=["suppliers"],
)


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
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
    response_model=Union[list[SupplierResponse], SupplierEmptyResponse],
)
def list_suppliers(
    search: Optional[str] = Query(None, description="Search by name, phone, contact person, or GSTIN"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).list_suppliers(
        tenant_id=user.tenant_id,
        search=search,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/search",
    response_model=Union[list[SupplierResponse], SupplierEmptyResponse],
)
def search_suppliers(
    search: str = Query(
        ...,
        min_length=1,
        max_length=255,
        description="Search supplier by name, phone, contact person, or GSTIN",
    ),
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    search_clean = search.strip()
    if not search_clean:
        raise HTTPException(
            status_code=422,
            detail="Search term cannot be empty or whitespace",
        )
    return SupplierService(db).search_suppliers(
        user.tenant_id,
        search_clean,
    )




@router.get(
    "/summary",
    response_model=SupplierSummaryResponse,
)
def suppliers_summary(
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).get_suppliers_summary(
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
    status: Optional[str] = Query(None, description="Filter by purchase order status"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    user: User = Depends(
        require_permission("suppliers:read")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).get_purchase_history(
        user.tenant_id,
        supplier_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{supplier_id}/products",
    response_model=SupplierProductsResponse,
)
def get_supplier_products(
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
    return SupplierService(db).get_supplier_products(
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


@router.delete(
    "/{supplier_id}",
    response_model=SupplierDeleteResponse,
)
def delete_supplier(
    supplier_id: int = Path(
        ...,
        gt=0,
        description="Supplier ID must be greater than zero",
    ),
    user: User = Depends(
        require_permission("suppliers:write")
    ),
    db: Session = Depends(get_db),
):
    return SupplierService(db).delete_supplier(
        user.tenant_id,
        supplier_id,
    )