import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALLOWED_PERIODS = {
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "yearly",
}

ALLOWED_STATUSES = {
    "active",
    "inactive",
    "completed",
    "cancelled",
}

TARGET_TYPE_REGEX = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+)*$")


class StoreTargetCreate(BaseModel):
    store_id: int = Field(
        ...,
        gt=0,
        description="The ID of the store to which this target applies",
    )

    target_type: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Target type (e.g. Sales, Revenue, Orders, New Customers)",
    )

    target_value: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("9999999999.99"),
        description="Target goal value (must be greater than 0 with at most 2 decimal places)",
    )

    period: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Target period: daily, weekly, monthly, quarterly, yearly",
    )

    start_date: datetime = Field(
        ...,
        description="Start date and time of the target period",
    )

    end_date: datetime = Field(
        ...,
        description="End date and time of the target period",
    )

    status: Optional[str] = Field(
        default="active",
        max_length=20,
        description="Target status: active, inactive, completed, cancelled",
    )

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Target type is required")
        if len(cleaned) < 2:
            raise ValueError("Target type must contain at least 2 characters")
        if len(cleaned) > 30:
            raise ValueError("Target type must not exceed 30 characters")
        if not TARGET_TYPE_REGEX.fullmatch(cleaned):
            raise ValueError(
                "Target type must contain only letters with a single space between words"
            )
        return cleaned

    @field_validator("target_value")
    @classmethod
    def validate_target_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Target value must be greater than 0")
        if value > Decimal("9999999999.99"):
            raise ValueError("Target value exceeds the maximum allowable limit of 9,999,999,999.99")
        # Check maximum 2 decimal places
        if value.as_tuple().exponent < -2:
            raise ValueError("Target value must not have more than 2 decimal places")
        return value

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in ALLOWED_PERIODS:
            sorted_periods = ", ".join(sorted(ALLOWED_PERIODS))
            raise ValueError(f"Period must be one of: {sorted_periods}")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> str:
        if value is None:
            return "active"
        cleaned = value.strip().lower()
        if cleaned not in ALLOWED_STATUSES:
            sorted_statuses = ", ".join(sorted(ALLOWED_STATUSES))
            raise ValueError(f"Status must be one of: {sorted_statuses}")
        return cleaned

    @model_validator(mode="after")
    def validate_date_range(self) -> "StoreTargetCreate":
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValueError("End date must be greater than start date")
        return self



class StoreTargetUpdate(BaseModel):
    target_type: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
        description="Updated target type",
    )

    target_value: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("9999999999.99"),
        description="Updated target goal value",
    )

    period: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Updated period: daily, weekly, monthly, quarterly, yearly",
    )

    start_date: Optional[datetime] = Field(
        default=None,
        description="Updated start date",
    )

    end_date: Optional[datetime] = Field(
        default=None,
        description="Updated end date",
    )

    status: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Updated status: active, inactive, completed, cancelled",
    )

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Target type cannot be empty")
        if len(cleaned) < 2:
            raise ValueError("Target type must contain at least 2 characters")
        if len(cleaned) > 30:
            raise ValueError("Target type must not exceed 30 characters")
        if not TARGET_TYPE_REGEX.fullmatch(cleaned):
            raise ValueError(
                "Target type must contain only letters with a single space between words"
            )
        return cleaned

    @field_validator("target_value")
    @classmethod
    def validate_target_value(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("Target value must be greater than 0")
        if value > Decimal("9999999999.99"):
            raise ValueError("Target value exceeds the maximum allowable limit of 9,999,999,999.99")
        if value.as_tuple().exponent < -2:
            raise ValueError("Target value must not have more than 2 decimal places")
        return value

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in ALLOWED_PERIODS:
            sorted_periods = ", ".join(sorted(ALLOWED_PERIODS))
            raise ValueError(f"Period must be one of: {sorted_periods}")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in ALLOWED_STATUSES:
            sorted_statuses = ", ".join(sorted(ALLOWED_STATUSES))
            raise ValueError(f"Status must be one of: {sorted_statuses}")
        return cleaned

    @model_validator(mode="after")
    def validate_date_range(self) -> "StoreTargetUpdate":
        if self.start_date is not None and self.end_date is not None:
            if self.end_date <= self.start_date:
                raise ValueError("End date must be greater than start date")
        return self


class StoreTargetResponse(BaseModel):
    id: int
    store_id: int
    target_type: str
    target_value: Decimal
    period: str
    start_date: datetime
    end_date: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StoreTargetProgressResponse(BaseModel):
    id: int
    store_id: int
    target_type: str
    target_value: Decimal
    current_value: Decimal
    achievement_percentage: float
    remaining_value: Decimal
    period: str
    start_date: datetime
    end_date: datetime
    status: str
    is_achieved: bool
    days_remaining: int

    model_config = ConfigDict(from_attributes=True)

