from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _calculate_denominations_total(denominations: Dict[str, int]) -> Decimal:
    total = Decimal("0.00")
    for note_str, count in denominations.items():
        if count < 0:
            raise ValueError(f"Denomination count for '{note_str}' cannot be negative")
        try:
            note_val = Decimal(str(note_str))
            if note_val <= Decimal("0"):
                raise ValueError(f"Denomination note '{note_str}' must be greater than zero")
        except Exception:
            raise ValueError(f"Invalid denomination note '{note_str}'")
        total += note_val * Decimal(count)
    return total


class POSShiftOpenRequest(BaseModel):
    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Store ID for the shift (optional; auto-selected for Admin/Owner if omitted)",
    )
    opening_cash_float: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Opening cash float amount in register drawer (must be >= 0)",
    )
    register_id: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Physical cash register or POS terminal ID (e.g. 'REG-01', 'Counter-1')",
    )
    denominations: Optional[Dict[str, int]] = Field(
        default=None,
        description="Opening cash denominations count e.g. {'500': 10, '200': 5, '100': 10}",
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

    @field_validator("register_id")
    @classmethod
    def validate_register_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            return s if s else None
        return None

    @model_validator(mode="after")
    def validate_denominations_match(self):
        if self.denominations:
            calc_total = _calculate_denominations_total(self.denominations)
            if self.opening_cash_float == Decimal("0.00"):
                self.opening_cash_float = calc_total
            elif self.opening_cash_float != calc_total:
                raise ValueError(
                    f"opening_cash_float ({self.opening_cash_float}) does not match denominations total ({calc_total})"
                )
        return self


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
    authorized_by: Optional[int] = Field(
        default=None,
        description="User ID of manager authorizing this cash movement",
    )
    authorization_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional manager authorization code or PIN",
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
    denominations: Optional[Dict[str, int]] = Field(
        default=None,
        description="Closing cash physical denominations count e.g. {'500': 15, '200': 10}",
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

    @model_validator(mode="after")
    def validate_closing_denominations(self):
        if self.denominations:
            calc_total = _calculate_denominations_total(self.denominations)
            if self.closing_cash_counted == Decimal("0.00") and calc_total > Decimal("0.00"):
                self.closing_cash_counted = calc_total
            elif self.closing_cash_counted != calc_total:
                raise ValueError(
                    f"closing_cash_counted ({self.closing_cash_counted}) does not match denominations total ({calc_total})"
                )
        return self


class POSForceCloseRequest(BaseModel):
    closing_cash_counted: Decimal = Field(
        ...,
        ge=0,
        description="Physical cash counted in drawer upon manager force close",
    )
    reason: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Mandatory manager reason for force closing the cashier's shift",
    )
    denominations: Optional[Dict[str, int]] = Field(
        default=None,
        description="Optional cash denominations count upon force close",
    )
    notes: Optional[str] = Field(default=None, max_length=500)

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
    register_id: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    closed_by: Optional[int] = None
    status: str
    opening_cash_float: Decimal
    opening_denominations: Optional[Dict[str, int]] = None
    closing_cash_counted: Optional[Decimal] = None
    closing_denominations: Optional[Dict[str, int]] = None
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
    register_id: Optional[str] = None
    closing_denominations: Optional[Dict[str, int]] = None
    closed_by: Optional[int] = None
    held_carts_warning: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class POSZReportResponse(BaseModel):
    shift_id: int
    status: str
    tenant_id: int
    store_id: int
    store_name: str
    cashier_id: int
    cashier_name: str
    register_id: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    closed_by: Optional[int] = None
    closed_by_name: Optional[str] = None
    opening_cash_float: Decimal
    opening_denominations: Optional[Dict[str, int]] = None
    cash_sales: Decimal
    cash_additions: Decimal
    cash_drops: Decimal
    cash_payouts: Decimal
    cash_refunds: Decimal
    expected_cash: Decimal
    closing_cash_counted: Optional[Decimal] = None
    closing_denominations: Optional[Dict[str, int]] = None
    cash_variance: Optional[Decimal] = None
    variance_status: str
    total_transactions: int
    total_sales_amount: Decimal
    payment_method_breakdown: Dict[str, Decimal]
    movements: List[POSCashMovementResponse]
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class POSXReportResponse(BaseModel):
    shift_id: int
    status: str
    tenant_id: int
    store_id: int
    store_name: str
    cashier_id: int
    cashier_name: str
    register_id: Optional[str] = None
    opened_at: datetime
    current_time: datetime
    opening_cash_float: Decimal
    cash_sales: Decimal
    cash_additions: Decimal
    cash_drops: Decimal
    cash_payouts: Decimal
    cash_refunds: Decimal
    current_drawer_cash: Decimal
    total_transactions: int
    total_sales_amount: Decimal
    payment_method_breakdown: Dict[str, Decimal]
    movements: List[POSCashMovementResponse]
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class POSShiftListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[POSShiftResponse]

    model_config = ConfigDict(from_attributes=True)


class POSShiftThermalMode(str, Enum):
    preview = "preview"
    view = "view"
    download = "download"
    pdf = "pdf"
    html = "html"
    json = "json"
    text = "text"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class POSShiftThermalResponse(BaseModel):
    success: bool = True
    message: str = "POS Shift Z-Report thermal slip generated successfully"
    shift_id: int
    store_name: str
    cashier_name: str
    text_payload: str
    html: str

