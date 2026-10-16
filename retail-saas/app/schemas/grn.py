from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class GRNItemCreate(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be positive")
    ordered_quantity: Optional[int] = Field(default=None, ge=0)
    received_quantity: int = Field(default=1, ge=1, description="Received quantity must be at least 1")
    unit_cost: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    remarks: Optional[str] = Field(default=None, max_length=500)


class GRNCreate(BaseModel):
    purchase_order_id: Optional[int] = Field(default=None, gt=0)
    warehouse_id: Optional[int] = Field(default=None, gt=0)
    store_id: Optional[int] = Field(default=None, gt=0)
    remarks: Optional[str] = Field(default=None, max_length=1000)
    items: list[GRNItemCreate] = Field(default_factory=list)


class GRNItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    ordered_quantity: int
    received_quantity: int
    unit_cost: Optional[Decimal] = None
    remarks: Optional[str] = None


class GRNResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    purchase_order_id: Optional[int] = None
    purchase_order_number: Optional[str] = None
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    grn_number: str
    status: str
    remarks: Optional[str] = None
    received_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    items: list[GRNItemResponse] = []


class GRNHistoryResponse(BaseModel):
    grn_id: int
    grn_number: str
    status: str
    created_at: datetime
    received_at: Optional[datetime] = None
    updated_at: datetime


class GRNPrintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grn_number: str
    tenant_id: int
    purchase_order_id: Optional[int] = None
    purchase_order_number: Optional[str] = None
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    status: str
    remarks: Optional[str] = None
    received_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: list[GRNItemResponse] = []


class GRNDeleteResponse(BaseModel):
    success: bool = True
    message: str
    id: int
