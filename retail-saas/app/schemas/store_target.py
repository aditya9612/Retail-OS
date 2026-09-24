import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class StoreTargetCreate(BaseModel):
    store_id: int = Field(gt=0)

    target_type: str = Field(
        min_length=1,
        max_length=30
    )

    target_value: Decimal = Field(gt=0)

    period: str = Field(
        min_length=1,
        max_length=20
    )

    start_date: datetime

    end_date: datetime

    @field_validator("store_id")
    @classmethod
    def validate_store_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "Store ID must be a positive number"
            )

        return value

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "Target type must not have leading or trailing spaces"
            )

        if not value:
            raise ValueError("Target type is required")

        if len(value) < 2:
            raise ValueError(
                "Target type must contain at least 2 characters"
            )

        if len(value) > 50:
            raise ValueError(
                "Target type must not exceed 50 characters"
            )


        if not re.fullmatch(
            r"[A-Za-z]+(?: [A-Za-z]+)*",
            value,
        ):
            raise ValueError(
                "Target type must contain only letters with a "
                "single space between words"
            )

        return value

    @field_validator("target_value")
    @classmethod
    def validate_target_value(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(
                "Target value must be greater than 0"
            )

        # Maximum 2 decimal places
        if round(value, 2) != value:
            raise ValueError(
                "Target value must not have more than 2 decimal places"
            )

        return value


    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:

        value = value.strip().lower()

        allowed_periods = {
            "daily",
            "weekly",
            "monthly",
            "yearly",
        }

        if value not in allowed_periods:
            raise ValueError(
                "Period must be one of: "
                "daily, weekly, monthly, yearly"
            )

        return value

    @field_validator("start_date")
    @classmethod
    def validate_start_date(
        cls,
        value: datetime,
    ) -> datetime:
        if value is None:
            raise ValueError(
                "Start date is required"
            )

        return value

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, v, info):
        start_date = info.data.get("start_date")

        if start_date and v <= start_date:
            raise ValueError(
                "End date must be greater than start date"
            )

        return v


class StoreTargetUpdate(BaseModel):
    target_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=30
    )

    target_value: Decimal | None = Field(
        default=None,
        gt=0
    )

    period: str | None = Field(
        default=None,
        min_length=1,
        max_length=20
    )

    start_date: datetime | None = None

    end_date: datetime | None = None

    status: str | None = Field(
        default=None,
        max_length=20
    )

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "Target type must not have leading or trailing spaces"
            )

        if not value:
            raise ValueError("Target type is required")

        if len(value) < 2:
            raise ValueError(
                "Target type must contain at least 2 characters"
            )

        if len(value) > 50:
            raise ValueError(
                "Target type must not exceed 50 characters"
            )


        if not re.fullmatch(
            r"[A-Za-z]+(?: [A-Za-z]+)*",
            value,
        ):
            raise ValueError(
                "Target type must contain only letters with a "
                "single space between words"
            )

        return value

    @field_validator("target_value")
    @classmethod
    def validate_target_value(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(
                "Target value must be greater than 0"
            )

        # Maximum 2 decimal places
        if round(value, 2) != value:
            raise ValueError(
                "Target value must not have more than 2 decimal places"
            )

        return value


    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:

        value = value.strip().lower()

        allowed_periods = {
            "daily",
            "weekly",
            "monthly",
            "yearly",
        }

        if value not in allowed_periods:
            raise ValueError(
                "Period must be one of: "
                "daily, weekly, monthly, yearly"
            )

        return value

    @field_validator("start_date")
    @classmethod
    def validate_start_date(
        cls,
        value: datetime,
    ) -> datetime:
        if value is None:
            raise ValueError(
                "Start date is required"
            )

        return value

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, v, info):
        start_date = info.data.get("start_date")

        if start_date and v <= start_date:
            raise ValueError(
                "End date must be greater than start date"
            )

        return v

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

    class Config:
        from_attributes = True
