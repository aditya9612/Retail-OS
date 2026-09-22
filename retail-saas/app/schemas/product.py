from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
    is_primary: bool = Field(default=False, description="Whether this is the primary product image")
    display_order: Optional[int] = Field(default=0, ge=0)

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
    is_primary: bool = False
    display_order: int = 0
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

    barcode: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Barcode",
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

    brand: Optional[str] = Field(default=None, max_length=100)

    selling_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("999999.99"),
        description="Selling price of the product",
    )

    cost_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("999999.99"),
    )

    tax_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=100,
        description="Tax rate percentage",
    )

    min_stock_alert: int = Field(default=5, ge=0)
    stock_status: str = Field(default="in_stock", max_length=50)
    unit: str = Field(default="pcs", max_length=50)
    is_active: bool = True

    # Compatibility fields
    price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"))
    gst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    variants: Optional[Dict[str, Any]] = None
    track_batch: bool = False
    track_expiry: bool = False
    image_url: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def reconcile_prices_and_taxes(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("selling_price") and data.get("price"):
                data["selling_price"] = data["price"]
            elif data.get("selling_price") and not data.get("price"):
                data["price"] = data["selling_price"]
            if not data.get("tax_rate") and data.get("gst_rate"):
                data["tax_rate"] = data["gst_rate"]
            elif data.get("tax_rate") and not data.get("gst_rate"):
                data["gst_rate"] = data["tax_rate"]
        return data

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

    brand: Optional[str] = None

    selling_price: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
    )

    cost_price: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
    )

    tax_rate: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=100,
    )

    min_stock_alert: Optional[int] = None
    stock_status: Optional[str] = None
    unit: Optional[str] = None
    is_active: Optional[bool] = None

    # Compatibility fields
    price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
    )
    gst_rate: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=100,
    )
    variants: Optional[Dict[str, Any]] = None
    track_batch: Optional[bool] = None
    track_expiry: Optional[bool] = None
    image_url: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="before")
    @classmethod
    def reconcile_update_prices_and_taxes(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("selling_price") and data.get("price"):
                data["selling_price"] = data["price"]
            elif data.get("selling_price") and not data.get("price"):
                data["price"] = data["selling_price"]
            if not data.get("tax_rate") and data.get("gst_rate"):
                data["tax_rate"] = data["gst_rate"]
            elif data.get("tax_rate") and not data.get("gst_rate"):
                data["gst_rate"] = data["tax_rate"]
        return data

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


class ProductResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    sku: str
    barcode: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    hsn_code: Optional[str] = None
    selling_price: Decimal
    cost_price: Decimal
    tax_rate: Decimal
    min_stock_alert: int = 5
    stock_status: str = "in_stock"
    unit: str = "pcs"
    price: Decimal
    gst_rate: Decimal
    variants: Optional[Dict[str, Any]] = None
    track_batch: bool = False
    track_expiry: bool = False
    image_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    images: list[ProductImageResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}