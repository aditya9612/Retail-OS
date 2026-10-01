from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator

class InventoryResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    product_id: int
    quantity: int
    min_stock_level: int = 0
    max_stock_level: int = 0
    reorder_point: int = 0
    low_stock_threshold: int = 10
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class LowStockResponse(BaseModel):
    success: bool
    message: str
    count: int
    data: list[InventoryResponse]

class InventoryValuationResponse(BaseModel):
    total_inventory_value: Decimal

class StockInRequest(BaseModel):
    store_id: int = Field(gt=0, description="Store ID must be positive")
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, le=100000, description="Quantity must be between 1 and 100000")
    supplier_id: Optional[int] = Field(default=None, gt=0)
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"))
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < date.today():
            raise ValueError("Expiry date cannot be in the past")
        return v

class StockOutRequest(BaseModel):
    store_id: int = Field(gt=0, description="Store ID must be positive")
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, le=100000, description="Quantity must be between 1 and 100000")
    notes: Optional[str] = Field(default=None, max_length=500)

class StockTransferRequest(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be positive")
    from_store_id: int = Field(gt=0, description="From Store ID must be positive")
    to_store_id: int = Field(gt=0, description="To Store ID must be positive")
    quantity: int = Field(gt=0, le=100000, description="Quantity must be between 1 and 100000")
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("to_store_id")
    @classmethod
    def validate_different_stores(cls, v: int, info: ValidationInfo) -> int:
        if "from_store_id" in info.data and v == info.data["from_store_id"]:
            raise ValueError("From store and To store cannot be the same")
        return v

class StockMovementResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    product_id: int
    movement_type: str
    quantity: int
    previous_stock: int = 0
    new_stock: int = 0
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class InventoryAdjustmentRequest(BaseModel):

    store_id: int = Field(
        gt=0,
        description="Store ID must be positive"
    )

    product_id: int = Field(
        gt=0,
        description="Product ID must be positive"
    )

    quantity: int = Field(
        gt=0,
        le=100000,
        description="Quantity must be between 1 and 100000"
    )

    adjustment_type: str = Field(
        pattern="^(increase|decrease)$"
    )

    reason: str = Field(
        min_length=2,
        max_length=500,
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:

        v = v.strip()

        if not v:
            raise ValueError(
                "Reason cannot be empty"
            )

        return v

class InventoryDashboardResponse(BaseModel):
    total_products: int
    total_stock: int
    total_stock_value: Decimal
    low_stock_items: int
    expired_products: int
    pending_transfers: int
    pending_purchase_orders: int

