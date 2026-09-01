from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

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
        gt=0,
        le=Decimal("999999999.99"),
        description="Minimum order amount must be greater than 0",
    )

    maximum_discount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999999.99"),
        description="Maximum discount must be greater than 0 when provided",
    )

    usage_limit: int = Field(
        ...,
        gt=0,
        description="Usage limit must be greater than 0",
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

        value = value.strip()

        if not value:
            raise ValueError(
                "Coupon code cannot be empty"
            )

        return value.upper()


    @field_validator("description")
    @classmethod
    def validate_description(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Description cannot be empty"
            )

        return value


    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(
        cls,
        value: str,
    ) -> str:

        value = value.strip().lower()

        if not value:
            raise ValueError(
                "Discount type cannot be empty"
            )

        if value not in ["percentage", "fixed"]:
            raise ValueError(
                "discount_type must be either 'percentage' or 'fixed'"
            )

        return value


    @model_validator(mode="after")
    def validate_coupon(self):

        if self.start_date < date.today():
            raise ValueError(
                "Start date cannot be in the past"
            )

        if self.end_date < self.start_date:
            raise ValueError(
                "End date must be on or after start date"
            )

        if (
            self.discount_type == "percentage"
            and self.discount_value > Decimal("100")
        ):
            raise ValueError(
                "Percentage discount cannot be greater than 100"
            )

        return self

class CouponCreate(CouponBase):

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": "string",
                "description": "string",
                "discount_type": "string",
                "discount_value": 1,
                "minimum_order_amount": 0,
                "maximum_discount": 0,
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
        gt=0,
        le=Decimal("999999999.99"),
    )

    maximum_discount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999999.99"),
    )

    usage_limit: Optional[int] = Field(
        default=None,
        gt=0,
    )

    start_date: Optional[date] = None

    end_date: Optional[date] = None

    is_active: Optional[bool] = None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "description": "string",
                "discount_value": 0,
                "minimum_order_amount": 0,
                "maximum_discount": 0,
                "usage_limit": 0,
                "start_date": "2026-08-27",
                "end_date": "2026-08-27",
                "is_active": True
            }
        }
    }

    @field_validator("description")
    @classmethod
    def validate_description(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
           return None

        value = value.strip()

        if not value:
           raise ValueError(
              "Description cannot be empty"
        )

        return value

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return None

        value = value.strip().lower()

        if value not in ["percentage", "fixed"]:
            raise ValueError(
                "discount_type must be either 'percentage' or 'fixed'"
            )

        return value

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
           and self.discount_value > Decimal("100")
        ):
            raise ValueError(
               "Percentage discount cannot be greater than 100"
            )

        return self

class CouponStatusUpdate(BaseModel):

    is_active: bool

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

    @field_validator("coupon_code")
    @classmethod
    def validate_coupon_code(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Coupon code cannot be empty"
            )

        return value.upper()


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

    @field_validator("coupon_code")
    @classmethod
    def validate_coupon_code(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "Coupon code cannot be empty"
            )

        return value.upper()


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
    scheduled_coupons: int
    total_used: int