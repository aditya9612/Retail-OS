from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class POSShiftOpenRequest(BaseModel):
    opening_cash_float: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Opening cash float amount in register drawer (must be >= 0)",
    )
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional opening shift notes")

    @field_validator("opening_cash_float", mode="before")
    @classmethod
    def validate_opening_cash_float(cls, v):
        if v is None:
            return Decimal("0.00")
        try:
            val = Decimal(str(v))
        except Exception:
            raise ValueError("opening_cash_float must be a valid number")
        if val < Decimal("0.00"):
            raise ValueError("opening_cash_float must be greater than or equal to 0")
        return val


class POSCashMovementRequest(BaseModel):
    movement_type: Literal["CASH_DROP", "CASH_PAYOUT", "CASH_IN"] = Field(
        ...,
        description="Type of cash movement: CASH_DROP (deposit to safe), CASH_PAYOUT (petty cash out), CASH_IN (cash addition)",
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount of cash moved (must be > 0)",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Non-empty explanation for cash movement",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v):
        try:
            val = Decimal(str(v))
        except Exception:
            raise ValueError("amount must be a valid number")
        if val <= Decimal("0.00"):
            raise ValueError("amount must be greater than 0")
        return val

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("reason cannot be empty or whitespace")
        return s


class POSCashMovementResponse(BaseModel):
    id: int
    shift_id: int
    movement_type: str
    amount: Decimal
    reason: str
    created_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class POSShiftCloseRequest(BaseModel):
    closing_cash_counted: Decimal = Field(
        ...,
        ge=0,
        description="Total physical cash counted in drawer at shift close",
    )
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional closing shift notes")

    @field_validator("closing_cash_counted", mode="before")
    @classmethod
    def validate_closing_cash(cls, v):
        try:
            val = Decimal(str(v))
        except Exception:
            raise ValueError("closing_cash_counted must be a valid number")
        if val < Decimal("0.00"):
            raise ValueError("closing_cash_counted must be greater than or equal to 0")
        return val


class POSShiftResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    cashier_id: int
    opened_at: datetime
    closed_at: Optional[datetime] = None
    status: str
    opening_cash_float: Decimal
    closing_cash_counted: Optional[Decimal] = None
    expected_cash: Optional[Decimal] = None
    cash_variance: Optional[Decimal] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class POSShiftCloseResponse(BaseModel):
    shift: POSShiftResponse
    expected_cash: Decimal
    closing_cash_counted: Decimal
    cash_variance: Decimal
    variance_status: Literal["exact", "over", "short"]
    opening_cash_float: Decimal
    cash_sales: Decimal
    cash_additions: Decimal
    cash_drops: Decimal
    cash_payouts: Decimal
    cash_refunds: Decimal

    model_config = ConfigDict(from_attributes=True)


class POSZReportResponse(BaseModel):
    shift_id: int
    status: str
    tenant_id: int
    store_id: int
    store_name: str
    cashier_id: int
    cashier_name: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opening_cash_float: Decimal
    cash_sales: Decimal
    cash_additions: Decimal
    cash_drops: Decimal
    cash_payouts: Decimal
    cash_refunds: Decimal
    expected_cash: Decimal
    closing_cash_counted: Optional[Decimal] = None
    cash_variance: Optional[Decimal] = None
    variance_status: str
    total_transactions: int
    total_sales_amount: Decimal
    payment_method_breakdown: Dict[str, Decimal]
    movements: List[POSCashMovementResponse]
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

