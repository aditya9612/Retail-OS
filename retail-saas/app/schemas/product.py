from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    id: int
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    name: str
    sku: str
    barcode: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    hsn_code: Optional[str] = None
    gst_rate: Decimal = Field(default=Decimal("18.00"))
    price: Decimal
    cost_price: Decimal = Field(default=Decimal("0.00"))
    variants: Optional[Dict[str, Any]] = None
    track_batch: bool = False
    track_expiry: bool = False
    image_url: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    barcode: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    hsn_code: Optional[str] = None
    gst_rate: Optional[Decimal] = None
    price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    variants: Optional[Dict[str, Any]] = None
    track_batch: Optional[bool] = None
    track_expiry: Optional[bool] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
