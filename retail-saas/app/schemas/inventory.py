from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator, conint, EmailStr


class SupplierBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15, description="GSTIN must be exactly 15 characters")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("Phone must contain digits only")
        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) != 15:
            raise ValueError("GSTIN must be exactly 15 characters")
        return v.upper() if v else v


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    
    contact_person: Optional[str] = Field(None, min_length=2, max_length=100)
     
    email: EmailStr | None = None
    phone: str | None = Field(
         default=None,
         pattern=r"^(\+91)?[6-9]\d{9}$"
    )
    
    address: Optional[str] = None

    gstin: Optional[str] = None
    

class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    
    contact_person: Optional[str] = Field(None, min_length=2, max_length=100)
     
    email: EmailStr | None = None
    phone: str | None = Field(
         default=None,
         pattern=r"^(\+91)?[6-9]\d{9}$"
    )
    
    address: Optional[str] = None

    gstin: Optional[str] = None
    

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
    reference: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}