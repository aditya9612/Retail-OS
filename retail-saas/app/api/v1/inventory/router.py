from typing import Optional, Union

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_operational_write, require_permission
from app.models.user import User
from app.schemas.inventory import (
    BulkInventoryAdjustmentRequest,
    BulkInventoryAdjustmentResponse,
    ExpiryEmptyResponse,
    InventoryAdjustmentRequest,
    InventoryDashboardResponse,
    InventoryEmptyResponse,
    InventoryResponse,
    InventoryValuationBreakdownResponse,
    InventoryValuationResponse,
    LowStockResponse,
    NearExpiryResponse,
    ProductMultiStoreAvailabilityResponse,
    StockInRequest,
    StockInResponse,
    StockMovementEmptyResponse,
    StockMovementResponse,
    StockOutRequest,
    StockTransferRequest,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=Union[list[InventoryResponse], InventoryEmptyResponse])
def list_inventory(
    store_id: Optional[int] = Query(None, gt=0, description="Optional Store ID filter"),
    product_id: Optional[int] = Query(None, gt=0, description="Optional Product ID filter"),
    category_id: Optional[int] = Query(None, gt=0, description="Optional Category ID filter"),
    search: Optional[str] = Query(None, description="Search by product name or SKU"),
    low_stock_only: bool = Query(False, description="Filter only items at or below low stock threshold"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).list_inventory(
        tenant_id=user.tenant_id,
        store_id=store_id,
        product_id=product_id,
        category_id=category_id,
        search=search,
        low_stock_only=low_stock_only,
    )


@router.get("/near-expiry", response_model=NearExpiryResponse)
def get_near_expiry(
    days: int = Query(30, ge=1, le=365, description="Threshold in days to check for upcoming expiration"),
    store_id: Optional[int] = Query(None, gt=0, description="Optional Store ID filter"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_near_expiry_inventory(
        tenant_id=user.tenant_id,
        days=days,
        store_id=store_id,
    )


@router.get("/low-stock", response_model=LowStockResponse)
def low_stock(
    store_id: int = Query(..., gt=0, description="Store ID must be positive"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_low_stock(user.tenant_id, store_id)


@router.post("/stock-in", response_model=StockInResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def stock_in(
    data: StockInRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).stock_in(user.tenant_id, data)


@router.post("/stock-out", response_model=StockMovementResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def stock_out(
    data: StockOutRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).stock_out(user.tenant_id, data)


@router.post("/transfer", response_model=StockMovementResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def transfer_stock(
    data: StockTransferRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).transfer_stock(user.tenant_id, data)


@router.post("/bulk-adjust", response_model=BulkInventoryAdjustmentResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def bulk_adjust_inventory(
    data: BulkInventoryAdjustmentRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).bulk_adjust_inventory(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.get("/valuation/breakdown", response_model=InventoryValuationBreakdownResponse)
def inventory_valuation_breakdown(
    store_id: Optional[int] = Query(None, gt=0, description="Optional Store ID filter"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_valuation_breakdown(
        tenant_id=user.tenant_id,
        store_id=store_id,
    )


@router.get("/valuation", response_model=InventoryValuationResponse)
def inventory_valuation(
    store_id: Optional[int] = Query(None, gt=0, description="Optional Store ID filter"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).inventory_valuation(
        tenant_id=user.tenant_id,
        store_id=store_id,
    )


@router.get("/expiry", response_model=Union[list[InventoryResponse], ExpiryEmptyResponse])
def expiry_inventory(
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).expiry_inventory(
        user.tenant_id,
    )


@router.get("/movements", response_model=Union[list[StockMovementResponse], StockMovementEmptyResponse])
def list_movements(
    store_id: int = Query(..., gt=0, description="Store ID must be positive"),
    product_id: Optional[int] = Query(None, gt=0, description="Optional Product ID filter"),
    movement_type: Optional[str] = Query(None, description="Optional movement type filter"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Page size"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).list_movements(
        tenant_id=user.tenant_id,
        store_id=store_id,
        product_id=product_id,
        movement_type=movement_type,
        page=page,
        page_size=page_size,
    )


@router.post("/adjustment", response_model=StockMovementResponse, status_code=201, dependencies=[Depends(require_operational_write)])
def adjust_inventory(
    data: InventoryAdjustmentRequest,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).adjust_inventory(
        user.tenant_id,
        data,
    )


@router.get("/dashboard", response_model=InventoryDashboardResponse)
def inventory_dashboard(
    store_id: Optional[int] = Query(None, gt=0, description="Optional Store ID filter"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_dashboard(
        tenant_id=user.tenant_id,
        store_id=store_id,
    )


@router.get("/product/{product_id}/stores", response_model=ProductMultiStoreAvailabilityResponse)
def get_product_multi_store_stock(
    product_id: int = Path(..., gt=0, description="Product ID must be positive"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_product_availability_across_stores(
        tenant_id=user.tenant_id,
        product_id=product_id,
    )


@router.get("/{product_id}", response_model=InventoryResponse)
def get_inventory(
    product_id: int = Path(..., gt=0, description="Product ID must be positive"),
    store_id: Optional[int] = Query(None, gt=0, description="Optional Store ID to check stock for a specific store"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return InventoryService(db).get_inventory_by_product(
        tenant_id=user.tenant_id,
        product_id=product_id,
        store_id=store_id,
    )

