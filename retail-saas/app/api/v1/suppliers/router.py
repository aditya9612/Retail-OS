from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.inventory import SupplierCreate, SupplierUpdate, SupplierResponse, SupplierStatusUpdate, SupplierStatsResponse
from app.services.inventory_service import InventoryService
from app.schemas.purchase_order import PurchaseOrderResponse

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).list_suppliers(user.tenant_id)


@router.post("", response_model=SupplierResponse, status_code=201)
def create_supplier(
    data: SupplierCreate,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).create_supplier(user.tenant_id, data)


@router.get("/search", response_model=list[SupplierResponse],)
def search_suppliers(
    search: str,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).search_suppliers(
        user.tenant_id,
        search,
    )
    
@router.get("/stats", response_model=SupplierStatsResponse,)
def supplier_stats(
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).supplier_stats(
        user.tenant_id,
    )
    
    
@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_supplier(user.tenant_id, supplier_id)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).update_supplier(user.tenant_id, supplier_id, data)

  
@router.patch("/{supplier_id}/status", response_model=SupplierResponse,)
def update_supplier_status(
    supplier_id: int,
    data: SupplierStatusUpdate,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).update_supplier_status(
        user.tenant_id,
        supplier_id,
        data.is_active,
    ) 
    
@router.get("/{supplier_id}/purchase-history", response_model=list[PurchaseOrderResponse],)
def get_supplier_purchase_history(
    supplier_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_purchase_history(
        tenant_id=user.tenant_id,
        supplier_id=supplier_id,
    )  