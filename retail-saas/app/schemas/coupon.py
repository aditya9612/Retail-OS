from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CouponBase(BaseModel):
    code: str = Field(min_length=3, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)

    discount_type: str = Field(
        description="percentage or fixed"
    )

    discount_value: Decimal = Field(
        gt=0,
        le=Decimal("999999.99")
    )

    minimum_order_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0
    )

    maximum_discount: Optional[Decimal] = Field(
        default=None,
        ge=0
    )

    usage_limit: int = Field(
        default=1,
        ge=1
    )

    start_date: date
    end_date: date

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, value: str):
        value = value.lower()

        if value not in ["percentage", "fixed"]:
            raise ValueError(
                "discount_type must be percentage or fixed"
            )

        return value

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, value, info):

        if (
            "start_date" in info.data
            and value < info.data["start_date"]
        ):
            raise ValueError(
                "End date must be after start date"
            )

        return value


class CouponCreate(CouponBase):
    pass


class CouponUpdate(BaseModel):

    description: Optional[str] = None

    discount_value: Optional[Decimal] = None

    minimum_order_amount: Optional[Decimal] = None

    maximum_discount: Optional[Decimal] = None

    usage_limit: Optional[int] = None

    start_date: Optional[date] = None

    end_date: Optional[date] = None

    is_active: Optional[bool] = None


class CouponResponse(CouponBase):

    id: int

    tenant_id: int

    used_count: int

    is_active: bool

    created_at: datetime

    model_config = {
        "from_attributes": True
    }
    
    
class ValidateCouponRequest(BaseModel):
    coupon_code: str
    order_amount: Decimal = Field(gt=0)


class ValidateCouponResponse(BaseModel):
    valid: bool
    message: str
    
    
class ApplyCouponRequest(BaseModel):
     coupon_code: str
     order_amount: Decimal = Field(gt=0)


class ApplyCouponResponse(BaseModel):
    coupon_code: str
    original_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    message: str
    
class CouponStatsResponse(BaseModel):
    total_coupons: int
    active_coupons: int
    expired_coupons: int
    inactive_coupons: int
    total_used: int