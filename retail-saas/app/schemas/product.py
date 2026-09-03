from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

VALID_GST_SLABS = [
    Decimal("0"),
    Decimal("5"),
    Decimal("12"),
    Decimal("18"),
    Decimal("28"),
]


class CategoryBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    parent_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Category name cannot be empty or whitespace")
        return v


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    id: int
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductImageCreate(BaseModel):
    image_url: str = Field(min_length=1, max_length=500)
    display_order: int = Field(default=0, ge=0)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Image URL cannot be empty or whitespace")
        return v


class ProductImageResponse(BaseModel):
    id: int
    product_id: int
    image_url: str
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=255,
        description="Product name must be 2 to 255 characters",
    )

    sku: str = Field(
        min_length=2,
        max_length=100,
        description="SKU must be 2 to 100 characters",
    )

    barcode: str = Field(
        min_length=1,
        max_length=50,
        description="Barcode is required and cannot be blank",
    )

    description: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    category_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    hsn_code: Optional[str] = Field(
        default=None,
        min_length=4,
        max_length=8,
    )

    gst_rate: Decimal = Field(
        default=Decimal("18.00"),
        ge=0,
        le=100,
    )

    price: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Price must be greater than 0",
    )

    cost_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("999999.99"),
    )

    variants: Optional[Dict[str, Any]] = None
    track_batch: bool = False
    track_expiry: bool = False

    image_url: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Product name cannot be empty or whitespace")
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
    def validate_barcode(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("Barcode cannot be empty or whitespace")

        if not v.isdigit():
            raise ValueError("Barcode must contain digits only")

        if len(v) < 8 or len(v) > 50:
            raise ValueError("Barcode must contain between 8 and 50 digits")

        return v

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is not None:
            v = v.strip()

            if not v:
                raise ValueError("HSN code cannot be empty or whitespace")

            if not v.isdigit():
                raise ValueError("HSN code must contain digits only")

        return v

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_rate(
        cls,
        v: Decimal,
    ) -> Decimal:
        if v not in VALID_GST_SLABS:
            raise ValueError(
                f"GST rate must be one of "
                f"{[str(s) for s in VALID_GST_SLABS]}"
            )
        return v

    @field_validator("cost_price")
    @classmethod
    def validate_cost_price(
        cls,
        v: Decimal,
    ) -> Decimal:
        if v < 0:
            raise ValueError("Cost price cannot be negative")
        return v

    @field_validator("image_url")
    @classmethod
    def validate_image_url(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is not None:
            v = v.strip()

            if not v:
                raise ValueError("Image URL cannot be empty or whitespace")

        return v


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    barcode: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    category_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    hsn_code: Optional[str] = Field(
        default=None,
        min_length=4,
        max_length=8,
    )

    gst_rate: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=100,
    )

    price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
    )

    cost_price: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
    )

    variants: Optional[Dict[str, Any]] = None
    track_batch: Optional[bool] = None
    track_expiry: Optional[bool] = None

    image_url: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()

            if not v:
                raise ValueError("Product name cannot be empty or whitespace")

        return v

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()

            if not v:
                raise ValueError("Barcode cannot be empty or whitespace")

            if not v.isdigit():
                raise ValueError("Barcode must contain digits only")

            if len(v) < 8 or len(v) > 50:
                raise ValueError("Barcode must contain between 8 and 50 digits")

        return v

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is not None:
            v = v.strip()

            if not v:
                raise ValueError("HSN code cannot be empty or whitespace")

            if not v.isdigit():
                raise ValueError("HSN code must contain digits only")

        return v

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_rate(
        cls,
        v: Optional[Decimal],
    ) -> Optional[Decimal]:
        if v is not None and v not in VALID_GST_SLABS:
            raise ValueError(
                f"GST rate must be one of "
                f"{[str(s) for s in VALID_GST_SLABS]}"
            )
        return v

    @field_validator("image_url")
    @classmethod
    def validate_image_url(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is not None:
            v = v.strip()

            if not v:
                raise ValueError("Image URL cannot be empty or whitespace")

        return v


class ProductResponse(ProductBase):
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    images: list[ProductImageResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}