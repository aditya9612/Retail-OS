from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, EmailStr


class SupplierBase(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z ]+$"
    )
    
    contact_person: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z ]+$"
    )
    
    email: EmailStr | None = None
    phone: str | None = Field(
         default=None,
         pattern=r"^(\+91)?[6-9]\d{9}$"
    )
    
    address: str | None = Field(
        default=None,
        min_length=5,
        max_length=500
    )
    gstin: str | None = Field(
        default=None,
        pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
    )

class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z ]+$"
    )

    contact_person: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z ]+$"
    )
     
    email: EmailStr | None = None
    phone: str | None = Field(
         default=None,
         pattern=r"^(\+91)?[6-9]\d{9}$"
    )
    
    address: str | None = Field(
        default=None,
        min_length=5,
        max_length=500
    )

    gstin: str | None = Field(
        default=None,
        pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
    )
    

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
    store_id: int
    product_id: int
    quantity: int = Field(gt=0)
    supplier_id: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None


class StockOutRequest(BaseModel):
    store_id: int
    product_id: int
    quantity: int = Field(gt=0)
    notes: Optional[str] = None


class StockTransferRequest(BaseModel):
    product_id: int
    from_store_id: int
    to_store_id: int
    quantity: int = Field(gt=0)
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
