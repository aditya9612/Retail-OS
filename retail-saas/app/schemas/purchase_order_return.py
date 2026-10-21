from datetime import datetime
from decimal import Decimal
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DISALLOWED_RETURN_PLACEHOLDERS = {
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "n/a",
    "na",
    "null value",
    "dummy",
    "sample",
    "unknown",
    "placeholder",
    "reason",
    "remarks",
}


def validate_text(
    value: Optional[str],
    field_name: str = "Reason",
    min_length: int = 3,
    max_length: int = 100,
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
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in DISALLOWED_RETURN_PLACEHOLDERS:
        raise ValueError(f"Please provide a valid {field_name.lower()}")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between {min_length} and {max_length} characters"
        )

    if v.isdigit():
        raise ValueError(f"{field_name} cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError(f"{field_name} must contain at least one alphabetic character")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repeating characters")

    if not re.fullmatch(r"[A-Za-z0-9\s,./#&'()\-:;!?]+", v):
        raise ValueError(f"{field_name} contains invalid characters")

    return v


def validate_reference_code(
    value: Optional[str],
    field_name: str = "Reference",
    min_length: int = 2,
    max_length: int = 100,
) -> Optional[str]:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in DISALLOWED_RETURN_PLACEHOLDERS:
        raise ValueError(f"Please provide a valid {field_name.lower()}")

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(f"{field_name} must be between {min_length} and {max_length} characters")

    alnum_chars = [c.lower() for c in v if c.isalnum()]
    if alnum_chars and len(set(alnum_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repeating characters")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} must contain alphanumeric characters")

    if not re.fullmatch(r"[A-Za-z0-9/_\-\.]+", v):
        raise ValueError(f"{field_name} can contain only letters, numbers, '-', '_', '/', and '.'")

    return v


class PurchaseOrderReturnItemCreate(BaseModel):
    purchase_order_item_id: int = Field(
        gt=0,
        description="Purchase Order Item ID must be positive",
    )
    quantity: int = Field(
        gt=0,
        le=100000,
        description="Return quantity must be between 1 and 100000",
    )
    batch_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Batch number being returned",
    )
    item_reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Specific reason for this item return (e.g., Damaged, Expired)",
    )

    @field_validator("batch_number")
    @classmethod
    def validate_batch(cls, value: Optional[str]) -> Optional[str]:
        return validate_reference_code(value, "Batch number", 2, 100)

    @field_validator("item_reason")
    @classmethod
    def validate_item_reason(cls, value: Optional[str]) -> Optional[str]:
        return validate_text(value, "Item reason", 3, 255, required=False)


class PurchaseOrderReturnCreate(BaseModel):
    purchase_order_id: int = Field(
        gt=0,
        description="Purchase Order ID must be positive",
    )
    reason: str = Field(
        min_length=3,
        max_length=100,
    )
    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Origin store ID where return stock is located",
    )
    warehouse_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Origin warehouse ID where return stock is located",
    )
    debit_note_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional manual or supplier debit note reference number",
    )
    items: list[PurchaseOrderReturnItemCreate] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return validate_text(
            value,
            "Reason",
            3,
            100,
            required=True,
        )

    @field_validator("debit_note_number")
    @classmethod
    def validate_debit_note(cls, value: Optional[str]) -> Optional[str]:
        return validate_reference_code(value, "Debit note number", 2, 100)

    @field_validator("items")
    @classmethod
    def validate_items(
        cls,
        value: list[PurchaseOrderReturnItemCreate],
    ):
        if not value:
            raise ValueError(
                "At least one return item is required"
            )

        item_ids = [
            item.purchase_order_item_id
            for item in value
        ]

        if len(item_ids) != len(set(item_ids)):
            raise ValueError(
                "Duplicate Purchase Order Item IDs are not allowed in a single return"
            )

        return value


class PurchaseOrderReturnUpdate(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
    )
    debit_note_number: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    items: Optional[list[PurchaseOrderReturnItemCreate]] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: Optional[str]):
        if value is None:
            return None

        return validate_text(
            value,
            "Reason",
            3,
            100,
            required=False,
        )

    @field_validator("debit_note_number")
    @classmethod
    def validate_debit_note(cls, value: Optional[str]) -> Optional[str]:
        return validate_reference_code(value, "Debit note number", 2, 100)

    @model_validator(mode="after")
    def validate_update(self):
        if self.reason is None and self.debit_note_number is None and self.items is None:
            raise ValueError(
                "At least one field must be provided for update"
            )
        return self


class PurchaseOrderReturnRejectRequest(BaseModel):
    rejection_reason: str = Field(
        min_length=3,
        max_length=500,
        description="Mandatory explanation for rejecting the purchase order return",
    )

    @field_validator("rejection_reason")
    @classmethod
    def validate_rejection(cls, value: str) -> str:
        return validate_text(value, "Rejection reason", 3, 500, required=True)


class PurchaseOrderReturnStatusUpdate(BaseModel):
    status: str = Field(
        min_length=1,
        max_length=30,
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        value = value.strip().lower()
        allowed = {
            "requested",
            "approved",
            "rejected",
            "completed",
        }

        if value not in allowed:
            raise ValueError(
                "Status must be requested, approved, rejected or completed"
            )

        return value


class PurchaseOrderReturnItemResponse(BaseModel):
    id: int
    purchase_order_item_id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total: Decimal
    batch_number: Optional[str] = None
    item_reason: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class PurchaseOrderReturnResponse(BaseModel):
    id: int
    tenant_id: int
    return_number: str
    debit_note_number: Optional[str] = None
    purchase_order_id: int
    purchase_order_number: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    reason: str
    status: str
    total_amount: Decimal
    created_by_id: Optional[int] = None
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejected_by_id: Optional[int] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    items: list[PurchaseOrderReturnItemResponse] = []

    model_config = ConfigDict(
        from_attributes=True
    )


class PurchaseOrderReturnPaginatedResponse(BaseModel):
    items: list[PurchaseOrderReturnResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class TopReturnReasonItem(BaseModel):
    reason: str
    count: int
    total_amount: Decimal


class PurchaseOrderReturnStatsResponse(BaseModel):
    total_returns: int
    requested_count: int
    approved_count: int
    completed_count: int
    rejected_count: int
    total_debit_amount: Decimal
    top_reasons: list[TopReturnReasonItem] = []