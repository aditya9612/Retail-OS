from datetime import datetime
from decimal import Decimal
import re
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class SaaSPlanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Plan display name")
    description: Optional[str] = Field(None, description="Plan description")
    price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Plan price in Decimal")
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO currency code")
    billing_interval: str = Field(default="monthly", description="Billing interval (monthly or yearly)")
    trial_days: int = Field(default=14, ge=0, description="Trial duration in days")
    is_active: bool = Field(default=True, description="Whether the plan is actively available in catalog")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Plan name cannot be empty")
        if len(value) > 100:
            raise ValueError("Plan name cannot exceed 100 characters")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3:
            raise ValueError("Currency must be exactly 3 characters")
        return value

    @field_validator("billing_interval")
    @classmethod
    def validate_billing_interval(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in ("monthly", "yearly"):
            raise ValueError("Billing interval must be 'monthly' or 'yearly'")
        return value

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: Decimal) -> Decimal:
        if value < Decimal("0.00"):
            raise ValueError("Price cannot be negative")
        return value.quantize(Decimal("0.01"))


class SaaSPlanCreate(SaaSPlanBase):
    code: str = Field(..., min_length=1, max_length=50, description="Unique plan identifier code")

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Plan code cannot be empty")
        if len(value) > 50:
            raise ValueError("Plan code cannot exceed 50 characters")
        if not re.match(r"^[a-z0-9_-]+$", value):
            raise ValueError("Plan code must contain only lowercase alphanumeric characters, underscores, or hyphens")
        return value


class SaaSPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=Decimal("0.00"))
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    billing_interval: Optional[str] = None
    trial_days: Optional[int] = Field(None, ge=0)

    @field_validator("name", "currency", "billing_interval", "price", "trial_days", mode="before")
    @classmethod
    def validate_non_null(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Plan name cannot be empty")
            if len(value) > 100:
                raise ValueError("Plan name cannot exceed 100 characters")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = value.strip().upper()
            if len(value) != 3:
                raise ValueError("Currency must be exactly 3 characters")
        return value

    @field_validator("billing_interval")
    @classmethod
    def validate_billing_interval(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = value.strip().lower()
            if value not in ("monthly", "yearly"):
                raise ValueError("Billing interval must be 'monthly' or 'yearly'")
        return value

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None:
            if value < Decimal("0.00"):
                raise ValueError("Price cannot be negative")
            return value.quantize(Decimal("0.01"))
        return value


class SaaSPlanResponse(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str] = None
    price: Decimal
    currency: str
    billing_interval: str
    trial_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SaaSPlanListResponse(BaseModel):
    items: list[SaaSPlanResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
