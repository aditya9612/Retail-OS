from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_DISCOUNT_TYPES = {
    "percentage",
    "fixed",
    "coupon",
    "store_wide",
}


class CartItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    discount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    store_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Quantity must be greater than zero")
        return value

    @field_validator("unit_price")
    @classmethod
    def validate_unit_price(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value <= 0:
            raise ValueError("Unit price must be greater than zero")
        return value

    @field_validator("discount")
    @classmethod
    def validate_discount(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("Discount cannot be negative")
        return value


class CartItemUpdate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    discount: Optional[Decimal] = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value <= 0:
            raise ValueError("Quantity must be greater than zero")
        return value

    @field_validator("unit_price")
    @classmethod
    def validate_unit_price(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value <= 0:
            raise ValueError("Unit price must be greater than zero")
        return value

    @field_validator("discount")
    @classmethod
    def validate_discount(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value < 0:
            raise ValueError("Discount cannot be negative")
        return value


class CartItemRemove(BaseModel):
    product_id: int = Field(gt=0)


class CartItemResponse(BaseModel):
    product_id: int
    product_name: str
    sku: str = ""
    hsn_code: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    gst_rate: Decimal
    gst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal


class CartDiscountApply(BaseModel):
    discount_type: str
    value: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    coupon_code: Optional[str] = Field(default=None, max_length=100)

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in VALID_DISCOUNT_TYPES:
            raise ValueError(
                "Discount type must be one of: percentage, fixed, coupon, store_wide"
            )
        return value

    @field_validator("value")
    @classmethod
    def validate_discount_value(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("Discount value cannot be negative")
        return value


class CartSummaryResponse(BaseModel):
    store_id: int
    customer_id: Optional[int]
    items: list[CartItemResponse]
    subtotal: Decimal
    discount_amount: Decimal
    gst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    grand_total: Decimal
    same_state: bool
    coupon_code: Optional[str] = None