from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductVariantBase(BaseModel):
    variant_name: str = Field(
        min_length=1,
        max_length=255,
        description="Name or title of variant (e.g., 'Size L - Navy Blue')",
    )
    sku: str = Field(
        min_length=2,
        max_length=100,
        description="Variant-specific SKU, unique within tenant",
    )
    barcode: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Variant-specific barcode, unique within tenant if provided",
    )
    size: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=50)
    attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Flexible attribute key-value pairs (e.g. {'material': 'cotton'})",
    )
    selling_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        description="Optional variant price override; if null, falls back to parent product",
    )
    cost_price: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
        description="Optional variant cost override; if null, falls back to parent product",
    )
    is_active: bool = True

    @field_validator("variant_name")
    @classmethod
    def validate_variant_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("variant_name cannot be empty or whitespace")
        return v

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("SKU cannot be empty or whitespace")
        return v.upper()

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if not v.isdigit():
                raise ValueError("Barcode must contain digits only")
            if len(v) < 8 or len(v) > 50:
                raise ValueError("Barcode must contain between 8 and 50 digits")
        return v

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError("attributes must be a dictionary")
            if len(v) > 50:
                raise ValueError("attributes dictionary cannot exceed 50 keys")
        return v


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantDirectCreate(ProductVariantBase):
    product_id: int = Field(gt=0, description="Parent Product ID to which this variant belongs")


class ProductVariantUpdate(BaseModel):
    variant_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sku: Optional[str] = Field(default=None, min_length=2, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=50)
    attributes: Optional[Dict[str, Any]] = None
    selling_price: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("999999.99"))
    cost_price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"))
    is_active: Optional[bool] = None

    @field_validator("variant_name")
    @classmethod
    def validate_variant_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("variant_name cannot be empty or whitespace")
        return v

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("SKU cannot be empty or whitespace")
            return v.upper()
        return v

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if not v.isdigit():
                raise ValueError("Barcode must contain digits only")
            if len(v) < 8 or len(v) > 50:
                raise ValueError("Barcode must contain between 8 and 50 digits")
        return v


class ProductVariantResponse(BaseModel):
    id: int
    tenant_id: int
    product_id: int
    variant_name: str
    sku: str
    barcode: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    selling_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    effective_selling_price: Decimal
    effective_cost_price: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductVariantListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductVariantResponse]

    model_config = ConfigDict(from_attributes=True)

