from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, conint


class SupplierBase(BaseModel):
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass

class SupplierResponse(SupplierBase):
    id: int
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    product_id: int
    quantity: int
    low_stock_threshold: int
    batch_number: Optional[str]
    expiry_date: Optional[date]
    created_at: datetime

    model_config = {"from_attributes": True}

class StockInRequest(BaseModel):
    store_id: conint(gt=0)
    product_id: conint(gt=0)
    quantity: conint(gt=0)

    supplier_id: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = Field(default=None, gt=0)
    notes: Optional[str] = None

class StockOutRequest(BaseModel):
    store_id: conint(gt=0)
    product_id: conint(gt=0)
    quantity: conint(gt=0)
    notes: Optional[str] = None

class StockTransferRequest(BaseModel):
    product_id: conint(gt=0)
    from_store_id: conint(gt=0)
    to_store_id: conint(gt=0)
    quantity: conint(gt=0)
    notes: Optional[str] = None

class StockMovementResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    product_id: int
    movement_type: str
    quantity: int
    reference: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}