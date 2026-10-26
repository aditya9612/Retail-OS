import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

DISALLOWED_CODE_PLACEHOLDERS = {
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "dummy",
    "sample",
    "na",
    "n/a",
}

DISALLOWED_DESCRIPTION_PLACEHOLDERS = {
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "dummy",
    "sample",
    "na",
    "n/a",
}


def validate_coupon_code_value(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError("Coupon code must be a string")
    value = value.strip()
    if not value:
        raise ValueError("Coupon code cannot be empty")
    if len(value) < 3 or len(value) > 50:
        raise ValueError("Coupon code must be between 3 and 50 characters")
    if value.lower() in DISALLOWED_CODE_PLACEHOLDERS:
        raise ValueError("Coupon code cannot be a placeholder")
    if not re.fullmatch(r"^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9]+$", value):
        raise ValueError("Coupon code must contain both letters and digits without spaces or special characters")
    return value.upper()


def validate_description_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError("Description must be a string")
    value = value.strip()
    if not value:
        raise ValueError("Description cannot be empty")
    if len(value) < 3 or len(value) > 255:
        raise ValueError("Description must be between 3 and 255 characters")
    if value.lower() in DISALLOWED_DESCRIPTION_PLACEHOLDERS:
        raise ValueError("Description cannot be a placeholder")
    if not any(c.isalpha() for c in value):
        raise ValueError("Description must contain meaningful text with at least one letter")
    return value


def validate_date_value(value: Any, field_name: str = "Date") -> date:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} cannot be a boolean")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string in YYYY-MM-DD format")
    value = value.strip()
    if not re.fullmatch(r"^\d{4}-\d{2}-\d{2}$", value):
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid calendar date for {field_name} in YYYY-MM-DD format")


def validate_discount_type_value(value: Any, required: bool = True) -> Optional[str]:
    if value is None:
        if required:
            raise ValueError("discount_type must be either 'percentage' or 'fixed'")
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError("discount_type must be either 'percentage' or 'fixed'")
    value = value.strip().lower()
    if not value or value not in ("percentage", "fixed"):
        raise ValueError("discount_type must be either 'percentage' or 'fixed'")
    return value


def validate_decimal_amount(
    value: Any,
    field_name: str,
    allow_zero: bool = False,
    min_value: Optional[Decimal] = None,
    max_value: Decimal = Decimal("999999999.99"),
) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number, not a boolean")
    if not isinstance(value, (int, float, Decimal, str)):
        raise ValueError(f"{field_name} must be a numeric value")
    try:
        dec = Decimal(str(value))
    except Exception:
        raise ValueError(f"{field_name} must be a valid number")
    if dec.is_nan() or dec.is_infinite():
        raise ValueError(f"{field_name} cannot be NaN or infinity")
    if min_value is not None:
        if dec < min_value:
            raise ValueError(f"{field_name} must be greater than or equal to {min_value}")
    elif allow_zero:
        if dec < Decimal("0"):
            raise ValueError(f"{field_name} cannot be negative")
    else:
        if dec <= Decimal("0"):
            raise ValueError(f"{field_name} must be greater than 0")
    if dec > max_value:
        raise ValueError(f"{field_name} exceeds maximum limit of {max_value}")
    if dec.as_tuple().exponent < -2:
        raise ValueError(f"{field_name} cannot have more than 2 decimal places")
    return dec


def validate_usage_limit_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or type(value) is not int:
        raise ValueError("Usage limit must be a positive whole integer")
    if value <= 0:
        raise ValueError("Usage limit must be greater than 0")
    if value > 2147483647:
        raise ValueError("Usage limit exceeds maximum allowed integer")
    return value


def validate_strict_bool_value(value: Any, field_name: str = "is_active") -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"Invalid value for {field_name}. Expected a boolean: true or false.")
    return value


class CouponBase(BaseModel):

    code: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Coupon code is required and must be 3-50 characters",
    )

    description: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Description is required and must be 3-255 characters",
    )

    discount_type: str = Field(
        ...,
        description="Discount type must be percentage or fixed",
    )

    discount_value: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("999999.99"),
        description="Discount value must be greater than 0",
    )

    minimum_order_amount: Decimal = Field(
        ...,
        ge=Decimal("1.00"),
        le=Decimal("999999999.99"),
        description="Minimum order amount must be greater than or equal to 1.00",
    )

    maximum_discount: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("1.00"),
        le=Decimal("999999999.99"),
        description="Maximum discount must be greater than or equal to 1.00 when provided",
    )

    usage_limit: int = Field(
        ...,
        gt=0,
        description="Usage limit must be greater than 0",
    )

    usage_limit_per_customer: Optional[int] = Field(
        default=None,
        gt=0,
        description="Usage limit per customer",
    )

    applicable_categories: Optional[list[str]] = Field(
        default=None,
        description="List of applicable category names or IDs",
    )

    applicable_products: Optional[list[str]] = Field(
        default=None,
        description="List of applicable product SKUs or IDs",
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional store ID restriction",
    )

    first_order_only: Optional[bool] = Field(
        default=False,
        description="Whether coupon applies to first order only",
    )

    start_date: date = Field(
        ...,
        description="Coupon start date",
    )

    end_date: date = Field(
        ...,
        description="Coupon end date",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return validate_coupon_code_value(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return validate_description_value(value)

    @field_validator("discount_type", mode="before")
    @classmethod
    def validate_discount_type(cls, value: Any) -> str:
        return validate_discount_type_value(value, required=True)

    @field_validator("discount_value", mode="before")
    @classmethod
    def validate_discount_value_field(cls, value: Any) -> Decimal:
        return validate_decimal_amount(value, "Discount value", allow_zero=False, max_value=Decimal("999999.99"))

    @field_validator("minimum_order_amount", mode="before")
    @classmethod
    def validate_minimum_order_amount_field(cls, value: Any) -> Decimal:
        return validate_decimal_amount(
            value,
            "Minimum order amount",
            min_value=Decimal("1.00"),
            max_value=Decimal("999999999.99"),
        )

    @field_validator("maximum_discount", mode="before")
    @classmethod
    def validate_maximum_discount_field(cls, value: Any) -> Optional[Decimal]:
        return validate_decimal_amount(
            value,
            "Maximum discount",
            min_value=Decimal("1.00"),
            max_value=Decimal("999999999.99"),
        )

    @field_validator("usage_limit", mode="before")
    @classmethod
    def validate_usage_limit_field(cls, value: Any) -> int:
        return validate_usage_limit_value(value)

    @field_validator("start_date", mode="before")
    @classmethod
    def validate_start_date_field(cls, value: Any) -> date:
        return validate_date_value(value, "Start date")

    @field_validator("end_date", mode="before")
    @classmethod
    def validate_end_date_field(cls, value: Any) -> date:
        return validate_date_value(value, "End date")

    @model_validator(mode="after")
    def validate_coupon(self):
        if self.start_date < date.today():
            raise ValueError("Start date cannot be in the past")

        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")

        if self.discount_type == "percentage":
            if self.discount_value < Decimal("1"):
                raise ValueError("Percentage discount must be greater than or equal to 1")
            if self.discount_value > Decimal("100"):
                raise ValueError("Percentage discount cannot be greater than 100")

        return self


class CouponCreate(CouponBase):

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": "string",
                "description": "string",
                "discount_type": "string",
                "discount_value": 1,
                "minimum_order_amount": 1,
                "maximum_discount": 1,
                "usage_limit": 1,
                "start_date": "2026-08-27",
                "end_date": "2026-08-27"
            }
        }
    }


class CouponUpdate(BaseModel):

    description: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=255,
    )

    discount_type: Optional[str] = Field(
        default=None,
    )

    discount_value: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
    )

    minimum_order_amount: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("1.00"),
        le=Decimal("999999999.99"),
    )

    maximum_discount: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("1.00"),
        le=Decimal("999999999.99"),
    )

    usage_limit: Optional[int] = Field(
        default=None,
        gt=0,
    )

    usage_limit_per_customer: Optional[int] = Field(
        default=None,
        gt=0,
    )

    applicable_categories: Optional[list[str]] = None
    applicable_products: Optional[list[str]] = None
    store_id: Optional[int] = None
    first_order_only: Optional[bool] = None

    start_date: Optional[date] = None

    end_date: Optional[date] = None

    is_active: Optional[bool] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "description": "string",
                "discount_value": 0,
                "minimum_order_amount": 1,
                "maximum_discount": 1,
                "usage_limit": 0,
                "start_date": "2026-08-27",
                "end_date": "2026-08-27",
                "is_active": True
            }
        }
    }

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        return validate_description_value(value)

    @field_validator("discount_type", mode="before")
    @classmethod
    def validate_discount_type(cls, value: Any) -> Optional[str]:
        return validate_discount_type_value(value, required=False)

    @field_validator("discount_value", mode="before")
    @classmethod
    def validate_discount_value_field(cls, value: Any) -> Optional[Decimal]:
        return validate_decimal_amount(value, "Discount value", allow_zero=False, max_value=Decimal("999999.99"))

    @field_validator("minimum_order_amount", mode="before")
    @classmethod
    def validate_minimum_order_amount_field(cls, value: Any) -> Optional[Decimal]:
        return validate_decimal_amount(
            value,
            "Minimum order amount",
            min_value=Decimal("1.00"),
            max_value=Decimal("999999999.99"),
        )

    @field_validator("maximum_discount", mode="before")
    @classmethod
    def validate_maximum_discount_field(cls, value: Any) -> Optional[Decimal]:
        return validate_decimal_amount(
            value,
            "Maximum discount",
            min_value=Decimal("1.00"),
            max_value=Decimal("999999999.99"),
        )

    @field_validator("usage_limit", mode="before")
    @classmethod
    def validate_usage_limit_field(cls, value: Any) -> Optional[int]:
        return validate_usage_limit_value(value)

    @field_validator("start_date", mode="before")
    @classmethod
    def validate_start_date_field(cls, value: Any) -> Optional[date]:
        if value is None:
            return None
        return validate_date_value(value, "Start date")

    @field_validator("end_date", mode="before")
    @classmethod
    def validate_end_date_field(cls, value: Any) -> Optional[date]:
        if value is None:
            return None
        return validate_date_value(value, "End date")

    @field_validator("is_active", mode="before")
    @classmethod
    def validate_is_active_field(cls, value: Any) -> Optional[bool]:
        return validate_strict_bool_value(value, "is_active")

    @model_validator(mode="after")
    def validate_update_values(self):
        if (
            self.start_date is not None
            and self.start_date < date.today()
        ):
            raise ValueError(
                "Start date cannot be in the past"
            )

        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError(
                "End date must be on or after start date"
            )

        if (
            self.discount_type == "percentage"
            and self.discount_value is not None
        ):
            if self.discount_value < Decimal("1"):
                raise ValueError(
                    "Percentage discount must be greater than or equal to 1"
                )
            if self.discount_value > Decimal("100"):
                raise ValueError(
                    "Percentage discount cannot be greater than 100"
                )

        return self


class CouponStatusUpdate(BaseModel):

    is_active: bool

    @field_validator("is_active", mode="before")
    @classmethod
    def validate_is_active(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValueError("Invalid value for is_active. Expected a boolean: true or false.")
        return value


class CouponResponse(BaseModel):

    id: int
    tenant_id: int
    code: str
    description: str
    discount_type: str
    discount_value: Decimal
    minimum_order_amount: Decimal
    maximum_discount: Optional[Decimal]
    usage_limit: int
    used_count: int
    usage_limit_per_customer: Optional[int] = None
    applicable_categories: Optional[list[str]] = None
    applicable_products: Optional[list[str]] = None
    store_id: Optional[int] = None
    first_order_only: bool = False
    is_deleted: bool = False
    start_date: date
    end_date: date
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ValidateCouponRequest(BaseModel):

    coupon_code: str = Field(
        ...,
        min_length=3,
        max_length=50,
    )

    order_amount: Decimal = Field(
        ...,
        gt=0,
        description="Order amount must be greater than 0",
    )
    customer_id: Optional[int] = Field(default=None, gt=0)
    customer_phone: Optional[str] = Field(default=None, max_length=20)
    store_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("coupon_code")
    @classmethod
    def validate_coupon_code(cls, value: str) -> str:
        return validate_coupon_code_value(value)

    @field_validator("order_amount", mode="before")
    @classmethod
    def validate_order_amount_field(cls, value: Any) -> Decimal:
        return validate_decimal_amount(value, "Order amount", allow_zero=False)


class ValidateCouponResponse(BaseModel):

    valid: bool
    message: str


class ApplyCouponRequest(BaseModel):

    coupon_code: str = Field(
        ...,
        min_length=3,
        max_length=50,
    )

    order_amount: Decimal = Field(
        ...,
        gt=0,
        description="Order amount must be greater than 0",
    )
    customer_id: Optional[int] = Field(default=None, gt=0)
    customer_phone: Optional[str] = Field(default=None, max_length=20)
    store_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("coupon_code")
    @classmethod
    def validate_coupon_code(cls, value: str) -> str:
        return validate_coupon_code_value(value)

    @field_validator("order_amount", mode="before")
    @classmethod
    def validate_order_amount_field(cls, value: Any) -> Decimal:
        return validate_decimal_amount(value, "Order amount", allow_zero=False)


class ApplyCouponResponse(BaseModel):

    coupon_code: str
    original_amount: float = Field(
        ...,
        description="Original order amount as a numeric value",
    )
    discount_amount: float = Field(
        ...,
        description="Discount amount applied as a numeric value",
    )
    final_amount: float = Field(
        ...,
        ge=0,
        description="Final payable amount as a non-negative numeric value",
    )
    message: str

    @field_validator("original_amount", "discount_amount", "final_amount", mode="before")
    @classmethod
    def validate_and_round_amounts(cls, value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError("Amount cannot be a boolean")
        try:
            return float(round(Decimal(str(value)), 2))
        except Exception:
            raise ValueError("Amount must be a numeric value")

    @field_validator("final_amount")
    @classmethod
    def ensure_non_negative_final(cls, value: float) -> float:
        if value < 0:
            return 0.0
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "coupon_code": "SAVE10",
                "original_amount": 100.0,
                "discount_amount": 10.0,
                "final_amount": 90.0,
                "message": "Coupon applied successfully"
            }
        }
    }


class CouponStatsResponse(BaseModel):

    total_coupons: int
    active_coupons: int
    expired_coupons: int
    inactive_coupons: int
    scheduled_coupons: int
    total_used: int


class CouponRedemptionResponse(BaseModel):
    id: int
    tenant_id: int
    coupon_id: int
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_phone: Optional[str] = None
    discount_amount: float
    order_amount: float
    redeemed_at: datetime

    model_config = {
        "from_attributes": True
    }


class BulkGenerateCouponsRequest(BaseModel):
    prefix: str = Field(..., min_length=2, max_length=20, description="Code prefix, e.g. FEST")
    count: int = Field(default=10, ge=1, le=500, description="Number of unique vouchers to generate")
    description: str = Field(..., min_length=3, max_length=255)
    discount_type: str = Field(..., description="Discount type: percentage or fixed")
    discount_value: Decimal = Field(..., gt=0)
    minimum_order_amount: Decimal = Field(default=Decimal("1.00"), ge=Decimal("1.00"))
    maximum_discount: Optional[Decimal] = None
    usage_limit: int = Field(default=1, gt=0)
    usage_limit_per_customer: Optional[int] = Field(default=1, gt=0)
    start_date: date
    end_date: date


class BulkGenerateCouponsResponse(BaseModel):
    success: bool = True
    message: str
    generated_count: int
    coupons: list[CouponResponse] = []


class ApplicableCouponItem(BaseModel):
    coupon: CouponResponse
    is_applicable: bool
    discount_amount: float
    final_amount: float
    message: str
    shortfall: Optional[float] = None


class ApplicableCouponsResponse(BaseModel):
    order_amount: float
    applicable_coupons: list[ApplicableCouponItem] = []
    locked_coupons: list[ApplicableCouponItem] = []
