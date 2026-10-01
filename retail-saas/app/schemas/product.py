from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Dict, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


VALID_GST_SLABS = [
    Decimal("0"),
    Decimal("5"),
    Decimal("12"),
    Decimal("18"),
    Decimal("28"),
]


PLACEHOLDER_VALUES = {
    "string",
    "null",
    "none",
    "undefined",
    "----",
    "---",
    "--",
    "- - -",
    "@#$%^",
    "!@#$%",
    "!@#$%^&*()",
    "test",
    "sample",
    "temp",
    "n/a",
    "na",
}


def validate_product_name(v: str) -> str:
    if v is None:
        raise ValueError("Product name cannot be null")

    if not isinstance(v, str):
        raise ValueError("Product name must be a string")

    v = v.strip()

    if not v:
        raise ValueError("Product name cannot be empty or whitespace")

    if len(v) < 2 or len(v) > 255:
        raise ValueError(
            "Product name must be between 2 and 255 characters"
        )

    if v.lower() in PLACEHOLDER_VALUES:
        raise ValueError(
            f"Product name cannot be placeholder '{v}'"
        )

    if re.fullmatch(r"^[-_.@#$%^&*!+=~`|<>?/\\]+$", v):
        raise ValueError(
            "Product name cannot consist only of special characters"
        )

    if v.isdigit() or re.fullmatch(r"^\d+$", v):
        raise ValueError(
            "Product name cannot consist only of numbers"
        )

    if not any(c.isalpha() for c in v):
        raise ValueError(
            "Product name must contain at least one letter"
        )

    if re.search(
        r"<\s*script|javascript\s*:|onload\s*=",
        v,
        re.IGNORECASE,
    ):
        raise ValueError(
            "Product name contains invalid script content"
        )

    return v


def validate_product_description(
    v: Optional[str],
) -> Optional[str]:
    if v is None:
        return None

    if not isinstance(v, str):
        raise ValueError("Description must be a string")

    v = v.strip()

    if not v:
        raise ValueError(
            "Description cannot be empty or whitespace"
        )

    if len(v) < 3 or len(v) > 1000:
        raise ValueError(
            "Description must be between 3 and 1000 characters"
        )

    if v.lower() in PLACEHOLDER_VALUES:
        raise ValueError(
            f"Description cannot be placeholder '{v}'"
        )

    if re.fullmatch(r"^[-_.@#$%^&*!+=~`|<>?/\\]+$", v):
        raise ValueError(
            "Description cannot consist only of special characters"
        )

    if v.isdigit() or re.fullmatch(r"^\d+$", v):
        raise ValueError(
            "Description cannot consist only of numbers"
        )

    if not any(c.isalpha() for c in v):
        raise ValueError(
            "Description must contain at least one letter"
        )

    if re.search(
        r"<\s*script|javascript\s*:|onload\s*=",
        v,
        re.IGNORECASE,
    ):
        raise ValueError(
            "Description contains invalid script content"
        )

    return v


def validate_product_sku(v: str) -> str:
    if v is None:
        raise ValueError("SKU cannot be null")

    if not isinstance(v, str):
        raise ValueError("SKU must be a string")

    v = v.strip().upper()

    if not v:
        raise ValueError("SKU cannot be empty or whitespace")

    if v in (
        "STRING",
        "NULL",
        "NONE",
        "UNDEFINED",
        "TEST",
        "SAMPLE",
        "TEMP",
        "N/A",
        "NA",
    ):
        raise ValueError(
            f"SKU cannot be placeholder '{v}'"
        )

    if len(v) < 2 or len(v) > 100:
        raise ValueError(
            "SKU must be between 2 and 100 characters"
        )

    if re.fullmatch(r"^[-_.@#$%^&*!+=~`|<>?/\\]+$", v):
        raise ValueError(
            "SKU cannot consist only of special characters"
        )

    if not any(c.isalnum() for c in v):
        raise ValueError(
            "SKU must contain alphanumeric characters"
        )

    if not re.fullmatch(r"^[A-Z0-9_-]+$", v):
        raise ValueError(
            "SKU can only contain uppercase letters, numbers, hyphens, and underscores"
        )

    if re.search(
        r"<\s*script|javascript\s*:|onload\s*=",
        v,
        re.IGNORECASE,
    ):
        raise ValueError(
            "SKU contains invalid script content"
        )

    return v


def validate_product_barcode(
    v: Optional[str],
) -> Optional[str]:
    if v is None:
        return None

    if not isinstance(v, str):
        raise ValueError("Barcode must be a string")

    v = v.strip()

    if not v:
        raise ValueError(
            "Barcode cannot be empty or whitespace"
        )

    if v.lower() in (
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "sample",
        "temp",
        "n/a",
        "na",
    ):
        raise ValueError(
            f"Barcode cannot be placeholder '{v}'"
        )

    if not v.isdigit():
        raise ValueError(
            "Barcode must contain digits only"
        )

    if len(v) < 8 or len(v) > 50:
        raise ValueError(
            "Barcode must contain between 8 and 50 digits"
        )

    if len(set(v)) == 1:
        raise ValueError(
            "Barcode cannot consist of a single repeated digit"
        )

    return v


def validate_product_hsn_code(
    v: Optional[str],
) -> Optional[str]:
    if v is None:
        return None

    if not isinstance(v, str):
        raise ValueError("HSN code must be a string")

    v = v.strip()

    if not v:
        raise ValueError(
            "HSN code cannot be empty or whitespace"
        )

    if v.lower() in (
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "sample",
        "temp",
        "n/a",
        "na",
    ):
        raise ValueError(
            f"HSN code cannot be placeholder '{v}'"
        )

    if not v.isdigit():
        raise ValueError(
            "HSN code must contain digits only"
        )

    if len(v) not in (4, 6, 8):
        raise ValueError(
            "HSN code must contain exactly 4, 6, or 8 digits"
        )

    if len(set(v)) == 1:
        raise ValueError(
            "HSN code cannot consist of a single repeated digit"
        )

    return v


def validate_product_image_url(
    v: Optional[str],
    required: bool = False,
) -> Optional[str]:
    if v is None:
        if required:
            raise ValueError(
                "Image URL cannot be null"
            )
        return None

    if not isinstance(v, str):
        raise ValueError(
            "Image URL must be a string"
        )

    v = v.strip()

    if not v:
        if required:
            raise ValueError(
                "Image URL cannot be empty or whitespace"
            )
        return None

    if v.lower() in (
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "sample",
        "temp",
        "n/a",
        "na",
        "image_url",
    ):
        raise ValueError(
            f"Image URL cannot be placeholder '{v}'"
        )

    if len(v) > 500:
        raise ValueError(
            "Image URL cannot exceed 500 characters"
        )

    is_http = bool(
        re.match(
            r"^https?://[a-zA-Z0-9-._~:/?#\[\]@!$&'()*+,;=%]+$",
            v,
            re.IGNORECASE,
        )
    ) and (
        "." in v.split("://", 1)[1].split("/")[0]
    )

    is_path = bool(
        re.match(
            r"^/?uploads/[a-zA-Z0-9_./-]+$",
            v,
            re.IGNORECASE,
        )
    )

    if not (is_http or is_path):
        raise ValueError(
            "Image URL must be a valid HTTP/HTTPS URL or upload path (e.g. /uploads/products/image.png)"
        )

    return v


def validate_decimal_amount(
    value: Any,
    field_name: str = "Amount",
    gt_zero: bool = True,
    max_value: Decimal = Decimal("999999.99"),
) -> Decimal:
    if value is None:
        raise ValueError(
            f"{field_name} cannot be null"
        )

    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} cannot be a boolean"
        )

    if isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a number, not a string"
        )

    if isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, float):
        try:
            d = Decimal(str(value))
        except Exception:
            raise ValueError(
                f"{field_name} must be a valid decimal number"
            )
    elif isinstance(value, Decimal):
        d = value
    else:
        raise ValueError(
            f"{field_name} must be a valid numeric value"
        )

    if gt_zero:
        if d <= Decimal("0.00"):
            raise ValueError(
                f"{field_name} must be greater than 0"
            )
    else:
        if d < Decimal("0.00"):
            raise ValueError(
                f"{field_name} cannot be negative"
            )

    if d > max_value:
        raise ValueError(
            f"{field_name} cannot exceed {max_value}"
        )

    return d


def validate_strict_bool(
    value: Any,
    field_name: str,
) -> bool:
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    raise ValueError(
        f"{field_name} must be a boolean (true or false)"
    )


class BarcodeMode(str, Enum):
    DOWNLOAD = "download"
    PREVIEW = "preview"


class ProductImageCreate(BaseModel):
    image_url: str = Field(
        min_length=1,
        max_length=500,
    )

    is_primary: bool = Field(
        default=False,
        description="Whether this is the primary product image",
    )

    display_order: Optional[int] = Field(
        default=0,
        ge=0,
    )

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        result = validate_product_image_url(
            v,
            required=True,
        )
        return result or ""


class ProductImageResponse(BaseModel):
    id: int
    product_id: int
    image_url: str
    is_primary: bool = False
    display_order: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


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
        description="Barcode (8-50 digits)",
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
        description="HSN code (4, 6, or 8 digits)",
    )

    brand: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    selling_price: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Selling price must be greater than 0",
        json_schema_extra={
            "type": "number",
            "example": 99.99,
        },
    )

    mrp: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("999999.99"),
        description="MRP cannot be negative",
        json_schema_extra={
            "type": "number",
            "example": 120.00,
        },
    )

    tax_rate: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=100,
        description="Tax rate percentage",
        json_schema_extra={
            "type": "number",
            "example": 18.00,
        },
    )

    min_stock_alert: int = Field(
        default=5,
        ge=0,
    )

    stock_status: str = Field(
        default="in_stock",
        max_length=50,
    )

    unit: str = Field(
        default="pcs",
        max_length=50,
    )

    is_active: bool = True

    price: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
        json_schema_extra={
            "type": "number",
            "example": 99.99,
        },
    )

    gst_rate: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=100,
        json_schema_extra={
            "type": "number",
            "example": 18.00,
        },
    )

    variants: Optional[Dict[str, Any]] = None

    track_batch: bool = False

    track_expiry: bool = False

    batch_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Batch number (required when track_batch is true)",
    )

    expiry_date: Optional[date] = Field(
        default=None,
        description="Expiry date (required when track_expiry is true)",
    )

    image_url: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="before")
    @classmethod
    def reconcile_prices_and_taxes(
        cls,
        data: Any,
    ) -> Any:
        if isinstance(data, dict):
            if (
                not data.get("selling_price")
                and data.get("price") is not None
            ):
                data["selling_price"] = data["price"]

            elif (
                data.get("selling_price") is not None
                and not data.get("price")
            ):
                data["price"] = data["selling_price"]

            if (
                not data.get("tax_rate")
                and data.get("gst_rate") is not None
            ):
                data["tax_rate"] = data["gst_rate"]

            elif (
                data.get("tax_rate") is not None
                and not data.get("gst_rate")
            ):
                data["gst_rate"] = data["tax_rate"]

        return data

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return validate_product_name(v)

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        return validate_product_sku(v)

    @field_validator("barcode")
    @classmethod
    def validate_barcode(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_barcode(v)

    @field_validator("description")
    @classmethod
    def validate_desc(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_description(v)

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_hsn_code(v)

    @field_validator(
        "selling_price",
        mode="before",
    )
    @classmethod
    def validate_selling_price(
        cls,
        v: Any,
    ) -> Decimal:
        return validate_decimal_amount(
            v,
            "Selling price",
            gt_zero=True,
        )

    @field_validator(
        "price",
        mode="before",
    )
    @classmethod
    def validate_price(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        return validate_decimal_amount(
            v,
            "Price",
            gt_zero=False,
        )

    @field_validator(
        "mrp",
        mode="before",
    )
    @classmethod
    def validate_mrp(
        cls,
        v: Any,
    ) -> Decimal:
        return validate_decimal_amount(
            v,
            "MRP",
            gt_zero=False,
        )

    @field_validator(
        "tax_rate",
        mode="before",
    )
    @classmethod
    def validate_tax_rate(
        cls,
        v: Any,
    ) -> Decimal:
        return validate_decimal_amount(
            v,
            "Tax rate",
            gt_zero=False,
            max_value=Decimal("100.00"),
        )

    @field_validator(
        "gst_rate",
        mode="before",
    )
    @classmethod
    def validate_gst_rate_val(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        d = validate_decimal_amount(
            v,
            "GST rate",
            gt_zero=False,
            max_value=Decimal("100.00"),
        )

        if d not in VALID_GST_SLABS:
            raise ValueError(
                f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}"
            )

        return d

    @field_validator("image_url")
    @classmethod
    def validate_image_url(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_image_url(
            v,
            required=False,
        )

    @field_validator(
        "track_batch",
        mode="before",
    )
    @classmethod
    def validate_track_batch_field(
        cls,
        v: Any,
    ) -> bool:
        return validate_strict_bool(
            v,
            "track_batch",
        )

    @field_validator(
        "track_expiry",
        mode="before",
    )
    @classmethod
    def validate_track_expiry_field(
        cls,
        v: Any,
    ) -> bool:
        return validate_strict_bool(
            v,
            "track_expiry",
        )

    @model_validator(mode="after")
    def validate_product_integrity(self):
        if (
            self.mrp is not None
            and self.mrp > 0
            and self.mrp < self.selling_price
        ):
            raise ValueError(
                "MRP cannot be lower than selling price"
            )

        if self.barcode and self.sku == self.barcode:
            raise ValueError(
                "SKU and Barcode cannot have the same value"
            )

        if self.track_batch:
            if (
                not self.batch_number
                or not str(self.batch_number).strip()
            ):
                raise ValueError(
                    "batch_number is required when track_batch is true"
                )

            batch_value = str(
                self.batch_number
            ).strip()

            if batch_value.lower() in PLACEHOLDER_VALUES:
                raise ValueError(
                    f"Batch number cannot be placeholder '{batch_value}'"
                )

        if self.track_expiry:
            if not self.expiry_date:
                raise ValueError(
                    "expiry_date is required when track_expiry is true"
                )

            if self.expiry_date < date.today():
                raise ValueError(
                    "expiry_date cannot be in the past"
                )

        return self


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    sku: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    barcode: Optional[str] = Field(
        default=None,
        min_length=8,
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
        gt=0,
        le=Decimal("999999.99"),
        json_schema_extra={
            "type": "number",
            "example": 99.99,
        },
    )

    mrp: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
        json_schema_extra={
            "type": "number",
            "example": 120.00,
        },
    )

    tax_rate: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=100,
        json_schema_extra={
            "type": "number",
            "example": 18.00,
        },
    )

    min_stock_alert: Optional[int] = None
    stock_status: Optional[str] = None
    unit: Optional[str] = None
    is_active: Optional[bool] = None

    price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        json_schema_extra={
            "type": "number",
            "example": 99.99,
        },
    )

    gst_rate: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=100,
        json_schema_extra={
            "type": "number",
            "example": 18.00,
        },
    )

    variants: Optional[Dict[str, Any]] = None

    track_batch: Optional[bool] = None

    track_expiry: Optional[bool] = None

    batch_number: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    expiry_date: Optional[date] = Field(
        default=None,
    )

    image_url: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="before")
    @classmethod
    def reconcile_update_prices_and_taxes(
        cls,
        data: Any,
    ) -> Any:
        if isinstance(data, dict):
            if (
                not data.get("selling_price")
                and data.get("price") is not None
            ):
                data["selling_price"] = data["price"]

            elif (
                data.get("selling_price") is not None
                and not data.get("price")
            ):
                data["price"] = data["selling_price"]

            if (
                not data.get("tax_rate")
                and data.get("gst_rate") is not None
            ):
                data["tax_rate"] = data["gst_rate"]

            elif (
                data.get("tax_rate") is not None
                and not data.get("gst_rate")
            ):
                data["gst_rate"] = data["tax_rate"]

        return data

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is None:
            return None

        return validate_product_name(v)

    @field_validator("sku")
    @classmethod
    def validate_sku(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is None:
            return None

        return validate_product_sku(v)

    @field_validator("barcode")
    @classmethod
    def validate_barcode(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        if v is None:
            return None

        return validate_product_barcode(v)

    @field_validator("description")
    @classmethod
    def validate_desc(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_description(v)

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_hsn_code(v)

    @field_validator(
        "selling_price",
        mode="before",
    )
    @classmethod
    def validate_selling_price(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        return validate_decimal_amount(
            v,
            "Selling price",
            gt_zero=True,
        )

    @field_validator(
        "price",
        mode="before",
    )
    @classmethod
    def validate_price(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        return validate_decimal_amount(
            v,
            "Price",
            gt_zero=False,
        )

    @field_validator(
        "mrp",
        mode="before",
    )
    @classmethod
    def validate_mrp(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        return validate_decimal_amount(
            v,
            "MRP",
            gt_zero=False,
        )

    @field_validator(
        "tax_rate",
        mode="before",
    )
    @classmethod
    def validate_tax_rate(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        return validate_decimal_amount(
            v,
            "Tax rate",
            gt_zero=False,
            max_value=Decimal("100.00"),
        )

    @field_validator(
        "gst_rate",
        mode="before",
    )
    @classmethod
    def validate_gst_rate(
        cls,
        v: Any,
    ) -> Optional[Decimal]:
        if v is None:
            return None

        d = validate_decimal_amount(
            v,
            "GST rate",
            gt_zero=False,
            max_value=Decimal("100.00"),
        )

        if d not in VALID_GST_SLABS:
            raise ValueError(
                f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}"
            )

        return d

    @field_validator("image_url")
    @classmethod
    def validate_image_url(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        return validate_product_image_url(
            v,
            required=False,
        )

    @field_validator(
        "track_batch",
        mode="before",
    )
    @classmethod
    def validate_track_batch_field(
        cls,
        v: Any,
    ) -> Optional[bool]:
        if v is None:
            return None

        return validate_strict_bool(
            v,
            "track_batch",
        )

    @field_validator(
        "track_expiry",
        mode="before",
    )
    @classmethod
    def validate_track_expiry_field(
        cls,
        v: Any,
    ) -> Optional[bool]:
        if v is None:
            return None

        return validate_strict_bool(
            v,
            "track_expiry",
        )

    @model_validator(mode="after")
    def validate_update_integrity(self):
        if (
            self.mrp is not None
            and self.selling_price is not None
            and self.mrp > 0
            and self.mrp < self.selling_price
        ):
            raise ValueError(
                "MRP cannot be lower than selling price"
            )

        if (
            self.barcode
            and self.sku
            and self.sku == self.barcode
        ):
            raise ValueError(
                "SKU and Barcode cannot have the same value"
            )

        if self.track_batch is True:
            if (
                not self.batch_number
                or not str(self.batch_number).strip()
            ):
                raise ValueError(
                    "batch_number is required when track_batch is true"
                )

            batch_value = str(
                self.batch_number
            ).strip()

            if batch_value.lower() in PLACEHOLDER_VALUES:
                raise ValueError(
                    f"Batch number cannot be placeholder '{batch_value}'"
                )

        if self.track_expiry is True:
            if self.expiry_date is None:
                raise ValueError(
                    "expiry_date is required when track_expiry is true"
                )

            if self.expiry_date < date.today():
                raise ValueError(
                    "expiry_date cannot be in the past"
                )

        return self


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
    gst_rate: Decimal
    selling_price: Decimal
    mrp: Decimal
    tax_rate: Decimal
    min_stock_alert: int = 5
    stock_status: str = "in_stock"
    unit: str = "pcs"
    price: Decimal
    variants: Optional[Dict[str, Any]] = None
    track_batch: bool = False
    track_expiry: bool = False
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    image_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    images: list[ProductImageResponse] = Field(
        default_factory=list
    )

    @field_serializer(
        "selling_price",
        "mrp",
        "tax_rate",
        "gst_rate",
        "price",
        mode="plain",
        check_fields=False,
    )
    def serialize_decimal(
        self,
        v: Decimal,
    ) -> float:
        return float(v) if v is not None else 0.0

    model_config = ConfigDict(
        from_attributes=True
    )


class ProductLowStockResponse(ProductResponse):
    store_id: int = Field(
        description="Store ID where stock is low"
    )

    current_stock: int = Field(
        default=0,
        description="Current quantity in store",
    )

    quantity: int = Field(
        default=0,
        description="Current quantity in store (alias)",
    )

    threshold: int = Field(
        default=10,
        description="Low-stock threshold used for alert",
    )