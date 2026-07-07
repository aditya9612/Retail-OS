from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.inventory import (
    InventoryResponse,
    StockInRequest,
    StockMovementResponse,
    StockOutRequest,
    StockTransferRequest,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryResponse])
def list_inventory(
    store_id: int | None = None,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).list_inventory(user.tenant_id, store_id)


@router.get("/low-stock", response_model=list[InventoryResponse])
def low_stock(
    store_id: int | None = None,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_low_stock(user.tenant_id, store_id)


@router.post("/stock-in", response_model=StockMovementResponse, status_code=201)
def stock_in(
    data: StockInRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).stock_in(user.tenant_id, data)


@router.post("/stock-out", response_model=StockMovementResponse, status_code=201)
def stock_out(
    data: StockOutRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).stock_out(user.tenant_id, data)


@router.post("/transfer", response_model=StockMovementResponse, status_code=201)
def transfer_stock(
    data: StockTransferRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).transfer_stock(user.tenant_id, data)


@router.get("/movements", response_model=list[StockMovementResponse])
def list_movements(
    store_id: int | None = None,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).list_movements(user.tenant_id, store_id)


