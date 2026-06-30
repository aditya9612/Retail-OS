from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.inventory import SupplierCreate, SupplierResponse
from app.services.inventory_service import InventoryService

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


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_supplier(user.tenant_id, supplier_id)