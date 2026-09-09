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