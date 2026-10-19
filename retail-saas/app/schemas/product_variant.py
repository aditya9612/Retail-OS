
from datetime import datetime
from decimal import Decimal
import re
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

PRICE_MAX = Decimal("999999.99")

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{1,99}$")
BARCODE_PATTERN = re.compile(r"^[0-9]{8,50}$")


class ProductVariantBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_name: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=2, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)
    size: str = Field(min_length=1, max_length=50)
    color: str = Field(min_length=1, max_length=50)
    attributes: Dict[str, Any] = Field(
        description="Non-empty key-value attributes for this variant"
    )
    selling_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=PRICE_MAX,
        description="Optional variant selling-price override",
    )
    cost_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=PRICE_MAX,
        description="Optional variant cost-price override",
    )
    is_active: bool = True
    auto_generate_barcode: bool = Field(
        default=False,
        description="Auto-generate unique EAN-13 barcode if barcode is not provided",
    )

    @field_validator("variant_name")
    @classmethod
    def validate_variant_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "variant_name cannot be empty or whitespace"
            )

        if not any(character.isalnum() for character in value):
            raise ValueError(
                "variant_name must contain letters or numbers"
            )

        return value

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        value = value.strip().upper()

        if not SKU_PATTERN.fullmatch(value):
            raise ValueError(
                "SKU must be 2-100 characters and contain only "
                "letters, numbers, dot, underscore, slash, or hyphen"
            )

        return value

    @field_validator("barcode")
    @classmethod
    def validate_barcode(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "barcode cannot be empty; omit it if not available"
            )

        if not BARCODE_PATTERN.fullmatch(value):
            raise ValueError(
                "Barcode must contain 8 to 50 digits only"
            )

        return value

    @field_validator("size", "color")
    @classmethod
    def validate_required_text(
        cls,
        value: str,
        info,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                f"{info.field_name} cannot be empty or whitespace"
            )

        return value

    @field_validator("attributes")
    @classmethod
    def validate_attributes(
        cls,
        value: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise ValueError(
                "attributes must be a non-empty object"
            )

        if len(value) > 50:
            raise ValueError(
                "attributes cannot contain more than 50 keys"
            )

        cleaned: Dict[str, Any] = {}

        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    "Attribute keys cannot be empty"
                )

            cleaned_key = key.strip()

            if cleaned_key in cleaned:
                raise ValueError(
                    f"Duplicate attribute key after trimming: {cleaned_key}"
                )

            if item is None:
                raise ValueError(
                    f"Attribute '{cleaned_key}' cannot be null"
                )

            if isinstance(item, str) and not item.strip():
                raise ValueError(
                    f"Attribute '{cleaned_key}' cannot be empty"
                )

            cleaned[cleaned_key] = item

        return cleaned


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantDirectCreate(ProductVariantBase):
    product_id: int = Field(
        gt=0,
        description="Parent product ID",
    )


class ProductVariantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    sku: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
    )
    barcode: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    size: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    color: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    attributes: Optional[Dict[str, Any]] = None
    selling_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=PRICE_MAX,
    )
    cost_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=PRICE_MAX,
    )
    is_active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def validate_patch_input(cls, value):
        if not isinstance(value, dict):
            return value

        if not value:
            raise ValueError(
                "Provide at least one field to update"
            )

        for field_name in (
            "variant_name",
            "sku",
            "size",
            "color",
            "attributes",
            "is_active",
        ):
            if field_name in value and value[field_name] is None:
                raise ValueError(
                    f"{field_name} cannot be null"
                )

        for field_name in ("track_batch", "track_expiry"):
            if field_name in value:
                field_value = value[field_name]

                if not isinstance(field_value, bool):
                    raise ValueError(
                        f"{field_name} must be a boolean: true or false"
                    )

                raise ValueError(
                    f"{field_name} is a product-level field and "
                    "cannot be updated through the variant endpoint"
                )

        return value

    @model_validator(mode="after")
    def validate_patch_fields(self):
        if not self.model_fields_set:
            raise ValueError(
                "Provide at least one field to update"
            )

        return self

    @field_validator("variant_name")
    @classmethod
    def validate_variant_name(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return value

        value = value.strip()

        if not value or not any(
            character.isalnum() for character in value
        ):
            raise ValueError(
                "variant_name must contain letters or numbers"
            )

        return value

    @field_validator("sku")
    @classmethod
    def validate_sku(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return value

        value = value.strip().upper()

        if not SKU_PATTERN.fullmatch(value):
            raise ValueError(
                "SKU must be 2-100 characters and contain only "
                "letters, numbers, dot, underscore, slash, or hyphen"
            )

        return value

    @field_validator("barcode")
    @classmethod
    def validate_barcode(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "barcode cannot be empty; use null to clear it"
            )

        if not BARCODE_PATTERN.fullmatch(value):
            raise ValueError(
                "Barcode must contain 8 to 50 digits only"
            )

        return value

    @field_validator("size", "color")
    @classmethod
    def validate_optional_text(
        cls,
        value: Optional[str],
        info,
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                f"{info.field_name} cannot be empty or whitespace"
            )

        return value

    @field_validator("attributes")
    @classmethod
    def validate_optional_attributes(
        cls,
        value: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if value is None:
            return None

        if not value:
            raise ValueError(
                "attributes must be a non-empty object"
            )

        if len(value) > 50:
            raise ValueError(
                "attributes cannot contain more than 50 keys"
            )

        cleaned: Dict[str, Any] = {}

        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    "Attribute keys cannot be empty"
                )

            cleaned_key = key.strip()

            if cleaned_key in cleaned:
                raise ValueError(
                    f"Duplicate attribute key after trimming: {cleaned_key}"
                )

            if item is None:
                raise ValueError(
                    f"Attribute '{cleaned_key}' cannot be null"
                )

            if isinstance(item, str) and not item.strip():
                raise ValueError(
                    f"Attribute '{cleaned_key}' cannot be empty"
                )

            cleaned[cleaned_key] = item

        return cleaned


class ProductVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    product_name: Optional[str] = None

    @field_serializer(
        "selling_price",
        "cost_price",
        "effective_selling_price",
        "effective_cost_price",
        when_used="json",
    )
    def serialize_prices(
        self,
        value: Optional[Decimal],
    ) -> Optional[float]:
        if value is None:
            return None

        return float(value)


class ProductVariantListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    page: int
    page_size: int
    items: List[ProductVariantResponse]


class VariantMatrixGenerateRequest(BaseModel):
    product_id: int = Field(gt=0, description="Parent product ID to generate variants for")
    sizes: List[str] = Field(default=[], description="List of sizes (e.g. ['S', 'M', 'L'])")
    colors: List[str] = Field(default=[], description="List of colors (e.g. ['Black', 'White', 'Blue'])")
    attributes: Optional[Dict[str, Any]] = Field(default=None, description="Common attributes for all variants")
    selling_price: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("999999.99"))
    cost_price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"))
    sku_prefix: Optional[str] = Field(default=None, max_length=50, description="Optional custom SKU prefix")
    auto_generate_barcode: bool = Field(
        default=True,
        description="Automatically generate unique EAN-13 barcodes for all matrix variants",
    )

    @field_validator("sizes", "colors")
    @classmethod
    def clean_lists(cls, v: List[str]) -> List[str]:
        if v:
            return [item.strip() for item in v if item and item.strip()]
        return []

    @field_validator("sku_prefix")
    @classmethod
    def clean_prefix(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            return v if v else None
        return None


class VariantMatrixGenerateResponse(BaseModel):
    product_id: int
    product_name: str
    generated_count: int
    variants: List[ProductVariantResponse]


class VariantBarcodeGenerateResponse(BaseModel):
    success: bool = True
    message: str
    variant_id: int
    sku: str
    barcode: str


class VariantMissingBarcodesResponse(BaseModel):
    success: bool = True
    message: str
    updated_count: int
    variants: List[Dict[str, Any]]

