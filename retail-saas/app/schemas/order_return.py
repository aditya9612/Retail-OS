import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OrderReturnSlipMode(str, Enum):
    preview = "preview"
    view = "view"
    download = "download"
    html = "html"
    json = "json"


VALID_RETURN_STATUSES = [
    "requested",
    "approved",
    "rejected",
    "completed",
]

VALID_RETURN_TYPES = [
    "refund",
    "store_credit",
    "exchange",
]


class OrderReturnItemCreate(BaseModel):
    order_item_id: int = Field(
        ...,
        gt=0,
        description="Order item ID must be a positive integer",
    )
    quantity: int = Field(
        ...,
        gt=0,
        description="Quantity to return must be greater than zero",
    )
    condition: Optional[str] = Field(
        default="sellable",
        description="Condition of returned item: sellable, damaged, defective",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Item-level return reason",
    )

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: Optional[str]) -> str:
        if not value:
            return "sellable"
        val = value.strip().lower()
        if val not in {"sellable", "damaged", "defective"}:
            return "sellable"
        return val


class OrderReturnItemResponse(BaseModel):
    id: int
    order_return_id: int
    order_item_id: int
    product_id: int
    product_name: Optional[str] = None
    sku: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    condition: str
    reason: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

DISALLOWED_RETURN_PLACEHOLDERS = {
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "sample",
    "dummy",
    "temp",
    "n/a",
    "na",
    "null value",
    "unknown",
    "placeholder",
    "reason",
    "remarks",
}


def validate_return_text(
    value: Optional[str],
    field_name: str,
    min_length: int = 3,
    max_length: int = 500,
    required: bool = True,
) -> Optional[str]:
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        if required:
            raise ValueError(f"{field_name} cannot be empty or whitespace")
        return None

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    clean_norm = re.sub(r"[^a-zA-Z]", "", v.lower())
    if v.lower() in DISALLOWED_RETURN_PLACEHOLDERS or clean_norm in DISALLOWED_RETURN_PLACEHOLDERS:
        raise ValueError(f"Please provide a valid {field_name.lower()}")

    if v.isdigit():
        raise ValueError(f"{field_name} cannot contain only numbers")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(alpha_chars) < 3:
        raise ValueError(f"{field_name} must contain at least 3 alphabetic letters")

    if len(set(alpha_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repetitive characters")

    if re.search(r"[-+*/=_./\\|@#$%^&*!~`?]{2,}", v):
        raise ValueError(f"{field_name} cannot contain consecutive special characters")

    if not re.fullmatch(r"[A-Za-z0-9\s,./#&'()\-:;!?]+", v):
        raise ValueError(f"{field_name} contains invalid characters")

    return v


class OrderReturnCreate(BaseModel):
    order_id: int = Field(
        ...,
        gt=0,
        description="Order ID must be a positive integer",
    )

    customer_id: int = Field(
        ...,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    reason: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Return reason is required and must be 3-100 characters",
    )

    remarks: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Return remarks are optional (3-500 characters if provided)",
    )

    return_type: Optional[str] = Field(
        default="refund",
        description="Return type: refund, store_credit, or exchange",
    )

    items: list[OrderReturnItemCreate] = Field(
        default_factory=list,
        description="Optional list of items to return. If empty, all order items are returned.",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return validate_return_text(value, "Reason", min_length=3, max_length=100, required=True)

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: str | None) -> str | None:
        return validate_return_text(value, "Remarks", min_length=3, max_length=500, required=False)


    @field_validator("return_type")
    @classmethod
    def validate_return_type(cls, value: Optional[str]) -> str:
        if not value:
            return "refund"
        val = value.strip().lower()
        if val not in VALID_RETURN_TYPES:
            raise ValueError(
                f"Invalid return type. Allowed values: {VALID_RETURN_TYPES}"
            )
        return val

class OrderReturnUpdate(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Return reason must be 3-100 characters",
    )

    remarks: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Return remarks must be 3-500 characters",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        return validate_return_text(value, "Reason", min_length=3, max_length=100, required=False)

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: str | None) -> str | None:
        return validate_return_text(value, "Remarks", min_length=3, max_length=500, required=False)


class OrderReturnStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Return status",
    )

    remarks: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Remarks are required and must be 3-500 characters",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("Status cannot be empty")

        if value not in VALID_RETURN_STATUSES:
            raise ValueError(
                f"Invalid status. Allowed values: {VALID_RETURN_STATUSES}"
            )

        return value

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: str) -> str:
        return validate_return_text(value, "Remarks", min_length=3, max_length=500, required=True)


class OrderReturnRejectRequest(BaseModel):
    remarks: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Rejection reason is required and must be 3-500 characters",
    )

    @field_validator("remarks")
    @classmethod
    def validate_rejection_remarks(cls, value: str) -> str:
        return validate_return_text(value, "Rejection remarks", min_length=3, max_length=500, required=True)


class OrderReturnResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    customer_id: int
    return_number: Optional[str] = None
    return_type: str = "refund"
    total_amount: Decimal = Decimal("0.00")
    refund_amount: Decimal = Decimal("0.00")
    exchange_order_id: Optional[int] = None
    reason: str
    remarks: Optional[str] = None
    status: str
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejected_by_id: Optional[int] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    completed_by_id: Optional[int] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderReturnItemResponse] = Field(default_factory=list)

    model_config = {
        "from_attributes": True
    }


class OrderReturnStatsResponse(BaseModel):
    total_returns: int = 0
    requested_count: int = 0
    approved_count: int = 0
    completed_count: int = 0
    rejected_count: int = 0
    total_refund_amount: Decimal = Decimal("0.00")


class OrderReturnExchangeItem(BaseModel):
    product_id: int = Field(..., gt=0, description="Product ID for exchange")
    quantity: int = Field(..., gt=0, description="Quantity for exchange")
    variant_id: Optional[int] = Field(default=None, description="Optional product variant ID")
    unit_price: Optional[Decimal] = Field(default=None, description="Optional override unit price")


class OrderReturnExchangeRequest(BaseModel):
    exchange_items: list[OrderReturnExchangeItem] = Field(
        ...,
        min_length=1,
        description="At least one exchange item is required",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Exchange notes or customer instructions",
    )


class OrderReturnSlipItem(BaseModel):
    order_item_id: int
    product_id: int
    product_name: str
    sku: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    condition: str
    reason: Optional[str] = None


class OrderReturnSlipResponse(BaseModel):
    return_id: int
    return_number: str
    status: str
    return_type: str
    created_at: datetime
    order_id: int
    order_number: Optional[str] = None
    customer_id: int
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    total_amount: Decimal
    refund_amount: Decimal
    reason: str
    remarks: Optional[str] = None
    items: list[OrderReturnSlipItem] = Field(default_factory=list)
