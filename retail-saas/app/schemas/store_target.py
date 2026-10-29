import re
from enum import Enum
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    field_serializer,
)


ALLOWED_PERIODS = {
    "all",
    "daily",
    "weekly",
    "15_days",
    "15 days",
    "monthly",
    "quarterly",
    "yearly",
}

ORDERED_PERIODS = [
    "all",
    "daily",
    "weekly",
    "15_days",
    "monthly",
    "quarterly",
    "yearly",
]

ALLOWED_STATUSES = {
    "active",
    "inactive",
    "completed",
    "cancelled",
}


class TargetType(str, Enum):
    SALES = "Sales"
    REVENUE = "Revenue"
    PROFIT = "Profit"
    CUSTOMER_ACQUISITION = "Customer Acquisition"
    NEW_CUSTOMERS = "New Customers"
    ORDERS = "Orders"
    UNITS_SOLD = "Units Sold"
    CUSTOMER_RETENTION = "Customer Retention"


ALLOWED_TARGET_TYPES = {item.value for item in TargetType}

TARGET_TYPE_REGEX = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+)*$")


class StoreTargetCreate(BaseModel):
    store_id: int = Field(
        ...,
        gt=0,
        description="The ID of the store to which this target applies",
        examples=[1],
    )

    target_type: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Target type (e.g. Sales, Revenue, Orders, New Customers)",
        examples=["Sales Target"],
    )

    target_value: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("9999999999.99"),
        description="Target goal value (must be greater than 0 with at most 2 decimal places)",
        examples=[Decimal("50000.00")],
    )

    period: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Target period: all, daily, weekly, 15_days, monthly, quarterly, yearly",
        examples=["monthly"],
    )

    start_date: datetime = Field(
        ...,
        description="Start date and time of the target period",
        examples=["2026-10-01T00:00:00"],
    )

    end_date: datetime = Field(
        ...,
        description="End date and time of the target period",
        examples=["2026-10-31T23:59:59"],
    )

    status: Optional[str] = Field(
        default="active",
        max_length=20,
        description="Target status: active, inactive, completed, cancelled",
        examples=["active"],
    )

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
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
        words = set(cleaned.lower().split())
        allowed_keywords = (
            {t.value.lower() for t in TargetType}
            | {w.lower() for t in TargetType for w in t.value.split()}
            | {"target"}
        )
        if not (words & allowed_keywords or any(t.value.lower() in cleaned.lower() for t in TargetType)):
            allowed = ", ".join(sorted(ALLOWED_TARGET_TYPES))
            raise ValueError(
                f"Target type must be or include a supported target type: {allowed}"
            )
        return cleaned

    @field_validator("target_value")
    @classmethod
    def validate_target_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Target value must be greater than 0")

        if value > Decimal("9999999999.99"):
            raise ValueError(
                "Target value exceeds the maximum allowable limit "
                "of 9,999,999,999.99"
            )

        if value.as_tuple().exponent < -2:
            raise ValueError(
                "Target value must not have more than 2 decimal places"
            )

        return value

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        cleaned = value.strip().lower()

        if cleaned in ("15_days", "15 days"):
            return "15_days"

        if cleaned not in ALLOWED_PERIODS:
            allowed = ", ".join(ORDERED_PERIODS)
            raise ValueError(f"Period must be one of: {allowed}")

        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> str:
        if value is None:
            return "active"

        cleaned = value.strip().lower()

        if cleaned not in ALLOWED_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_STATUSES))
            raise ValueError(f"Status must be one of: {allowed}")

        return cleaned

    @model_validator(mode="after")
    def validate_date_range(self) -> "StoreTargetCreate":
        if self.end_date <= self.start_date:
            raise ValueError("End date must be greater than start date")

        return self


class StoreTargetUpdate(BaseModel):
    target_type: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
        description="Updated target type",
        examples=["Sales Target"],
    )

    target_value: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("9999999999.99"),
        description="Updated target goal value",
        examples=[Decimal("60000.00")],
    )

    period: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Updated period: all, daily, weekly, 15_days, monthly, quarterly, yearly",
        examples=["monthly"],
    )

    start_date: Optional[datetime] = Field(
        default=None,
        description="Updated start date",
        examples=["2026-10-01T00:00:00"],
    )

    end_date: Optional[datetime] = Field(
        default=None,
        description="Updated end date",
        examples=["2026-10-31T23:59:59"],
    )

    status: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Updated status: active, inactive, completed, cancelled",
        examples=["active"],
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
    def validate_target_value(
        cls, value: Optional[Decimal]
    ) -> Optional[Decimal]:
        if value is None:
            return None

        if value <= 0:
            raise ValueError("Target value must be greater than 0")

        if value > Decimal("9999999999.99"):
            raise ValueError(
                "Target value exceeds the maximum allowable limit "
                "of 9,999,999,999.99"
            )

        if value.as_tuple().exponent < -2:
            raise ValueError(
                "Target value must not have more than 2 decimal places"
            )

        return value

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        cleaned = value.strip().lower()

        if cleaned in ("15_days", "15 days"):
            return "15_days"

        if cleaned not in ALLOWED_PERIODS:
            allowed = ", ".join(ORDERED_PERIODS)
            raise ValueError(f"Period must be one of: {allowed}")

        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        cleaned = value.strip().lower()

        if cleaned not in ALLOWED_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_STATUSES))
            raise ValueError(f"Status must be one of: {allowed}")

        return cleaned

    @model_validator(mode="after")
    def validate_date_range(self) -> "StoreTargetUpdate":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date <= self.start_date
        ):
            raise ValueError("End date must be greater than start date")

        return self


class StoreTargetResponse(BaseModel):
    id: int = Field(..., description="Unique Store Target ID", examples=[1])
    store_id: int = Field(..., description="Target Store ID", examples=[2])
    store_name: Optional[str] = Field(None, description="Target Store Name", examples=["Main Retail Outlet"])
    store_code: Optional[str] = Field(None, description="Target Store Code", examples=["STR-MUM-01"])
    target_type: str = Field(..., description="Target Type", examples=["Sales Target"])
    target_value: Decimal = Field(..., description="Target Goal Value", examples=[Decimal("50000.00")])
    period: str = Field(..., description="Target Period (all, daily, weekly, 15_days, monthly, quarterly, yearly)", examples=["monthly"])
    start_date: datetime = Field(..., description="Start Date and Time")
    end_date: datetime = Field(..., description="End Date and Time")
    status: str = Field(..., description="Target Status (active, inactive, completed, cancelled)", examples=["active"])
    created_at: datetime = Field(..., description="Creation Timestamp")
    updated_at: datetime = Field(..., description="Last Update Timestamp")

    @field_serializer("target_value", mode="plain")
    def serialize_target_value(self, v: Decimal) -> float:
        return round(float(v), 2)

    model_config = ConfigDict(from_attributes=True)


class StoreTargetProgressResponse(BaseModel):
    id: int = Field(..., description="Unique Store Target ID", examples=[1])
    store_id: int = Field(..., description="Target Store ID", examples=[2])
    store_name: Optional[str] = Field(None, description="Target Store Name", examples=["Main Retail Outlet"])
    store_code: Optional[str] = Field(None, description="Target Store Code", examples=["STR-MUM-01"])
    target_type: str = Field(..., description="Target Type", examples=["Sales Target"])
    target_value: Decimal = Field(..., description="Target Goal Value", examples=[Decimal("50000.00")])
    current_value: Decimal = Field(..., description="Current Realized Value from Sales and Orders", examples=[Decimal("32500.00")])
    achievement_percentage: float = Field(..., description="Percentage of Goal Achieved", examples=[65.0])
    remaining_value: Decimal = Field(..., description="Remaining Value to Reach Goal", examples=[Decimal("17500.00")])
    period: str = Field(..., description="Target Period", examples=["monthly"])
    start_date: datetime = Field(..., description="Start Date and Time")
    end_date: datetime = Field(..., description="End Date and Time")
    status: str = Field(..., description="Target Status", examples=["active"])
    is_achieved: bool = Field(..., description="Whether Target Has Been Fully Achieved", examples=[False])
    days_remaining: int = Field(..., description="Days Remaining Until Target Period Closes", examples=[12])

    model_config = ConfigDict(from_attributes=True)


class StoreTargetLeaderboardItem(BaseModel):
    rank: int = Field(..., description="Store Ranking Position", examples=[1])
    target_id: int = Field(..., description="Target ID", examples=[10])
    store_id: int = Field(..., description="Store ID", examples=[2])
    store_name: str = Field(..., description="Store Name", examples=["Dadar Branch"])
    store_code: Optional[str] = Field(None, description="Store Code", examples=["STR-DADAR"])
    target_type: str = Field(..., description="Target Type", examples=["Sales Target"])
    target_value: Decimal = Field(..., description="Target Goal Value", examples=[Decimal("100000.00")])
    current_value: Decimal = Field(..., description="Current Realized Value", examples=[Decimal("112000.00")])
    achievement_percentage: float = Field(..., description="Achievement Percentage", examples=[112.0])
    remaining_value: Decimal = Field(..., description="Remaining Target Value", examples=[Decimal("0.00")])
    period: str = Field(..., description="Target Period", examples=["monthly"])
    is_achieved: bool = Field(..., description="Whether target has been met or exceeded", examples=[True])
    status: str = Field(..., description="Target Status", examples=["active"])

    model_config = ConfigDict(from_attributes=True)


class StoreTargetLeaderboardResponse(BaseModel):
    total_ranked: int = Field(..., description="Total Stores Ranked", examples=[5])
    period_filter: Optional[str] = Field(None, description="Active Period Filter", examples=["monthly"])
    target_type_filter: Optional[str] = Field(None, description="Active Target Type Filter", examples=["Sales Target"])
    leaderboard: list[StoreTargetLeaderboardItem] = Field(default_factory=list)


class StoreTargetSummaryResponse(BaseModel):
    total_targets: int = Field(default=0, description="Total active targets count", examples=[8])
    total_stores_with_targets: int = Field(default=0, description="Total distinct stores with active targets", examples=[5])
    total_target_value: Decimal = Field(default=Decimal("0.00"), description="Total monetary/order target value", examples=[Decimal("500000.00")])
    total_current_value: Decimal = Field(default=Decimal("0.00"), description="Total achieved value across targets", examples=[Decimal("320000.00")])
    overall_achievement_percentage: float = Field(default=0.0, description="Overall company-wide achievement rate", examples=[64.0])
    achieved_targets_count: int = Field(default=0, description="Count of targets meeting or exceeding 100%", examples=[3])
    on_track_targets_count: int = Field(default=0, description="Count of targets achieving 50%-99%", examples=[3])
    lagging_targets_count: int = Field(default=0, description="Count of targets achieving <50% or lagging near deadline", examples=[2])
    period: Optional[str] = Field(None, description="Period filter applied if any", examples=["monthly"])
