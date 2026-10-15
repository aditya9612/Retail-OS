from datetime import datetime
from decimal import Decimal
from enum import Enum
import math
import re
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


# ============================================================
# STATUS ENUM
# ============================================================

class StoreTransferStatus(str, Enum):
    DRAFT = "Draft"
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    DISPATCHED = "Dispatched"
    RECEIVED = "Received"

    @classmethod
    def list_values(cls) -> List[str]:
        return [item.value for item in cls]


# ============================================================
# VALIDATION HELPERS
# ============================================================

def validate_positive_integer_id(value: Any, field_name: str) -> int:
    """
    Validates that a given ID is a strict, positive whole integer (> 0).
    Rejects booleans, floats, non-integer decimals, non-digit strings,
    empty strings, whitespace strings, zero, and negative values.
    """
    if value is None:
        raise ValueError("Required field is not provided.")

    if isinstance(value, bool):
        raise ValueError(
            f"{field_name} must contain only whole numbers. "
            "Letters and special characters are not allowed."
        )

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(
                f"{field_name} must contain only whole numbers. "
                "Letters and special characters are not allowed."
            )
        if not value.is_integer():
            raise ValueError(
                f"{field_name} must contain only whole numbers. "
                "Letters, decimals and special characters are not allowed."
            )
        raise ValueError(
            f"{field_name} must be provided as a whole number"
        )

    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError(
                f"{field_name} must contain only whole numbers. "
                "Letters, decimals and special characters are not allowed."
            )
        raise ValueError(
            f"{field_name} must be provided as a whole number"
        )

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Required field is not provided.")
        if not cleaned.isdigit():
            raise ValueError(
                f"{field_name} must contain only whole numbers. "
                "Letters, decimals and special characters are not allowed."
            )
        value = int(cleaned)

    if not isinstance(value, int):
        raise ValueError(
            f"{field_name} must contain only whole numbers. "
            "Letters, decimals and special characters are not allowed."
        )

    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")

    return value


def validate_store_id(value: Any, field_name: str = "Store ID") -> int:
    """
    Validates store ID as a strict positive integer.
    """
    return validate_positive_integer_id(value, field_name)


def validate_staff_id(value: Any, field_name: str = "Staff ID") -> int:
    """
    Validates staff/user ID as a strict positive integer.
    """
    return validate_positive_integer_id(value, field_name)


def validate_transfer_status(value: Optional[str]) -> Optional[str]:
    """
    Validates transfer status string in a case-insensitive manner.
    Returns canonicalized status string (e.g. 'Pending', 'Approved').
    If None or empty, returns None.
    If invalid, raises ValueError listing all valid statuses.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            f"Invalid status '{value}'. Status must be a string."
        )

    cleaned = value.strip()
    if not cleaned:
        return None

    valid_statuses = {s.value.lower(): s.value for s in StoreTransferStatus}
    canonical = valid_statuses.get(cleaned.lower())
    if not canonical:
        allowed = ", ".join(StoreTransferStatus.list_values())
        raise ValueError(
            f"Invalid status '{cleaned}'. Valid statuses are: {allowed}"
        )

    return canonical


def validate_mobile_number(value: Optional[str]) -> Optional[str]:
    """
    Validates a 10-digit mobile number according to Indian mobile number standards (starting with 6, 7, 8, or 9).
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Mobile number must be a string")

    cleaned = value.strip()
    if not cleaned:
        return None

    # Strip out standard country code (+91 or 91) if present
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:].strip()
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:].strip()

    if not re.fullmatch(r"^[6-9]\d{9}$", cleaned):
        raise ValueError(
            "Invalid mobile number format. Must be a 10-digit number starting with 6, 7, 8, or 9."
        )

    return cleaned


# ============================================================
# ITEM SCHEMAS
# ============================================================

class StoreTransferItemBase(BaseModel):
    product_id: StrictInt = Field(
        ...,
        gt=0,
        description="Product ID must be a positive whole number",
    )

    quantity: StrictInt = Field(
        ...,
        gt=0,
        le=100000,
        description="Quantity must be a positive whole number between 1 and 100000",
    )

    @field_validator("product_id", mode="before")
    @classmethod
    def validate_product_id(cls, value):
        return validate_positive_integer_id(value, "Product ID")

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if isinstance(value, bool):
            raise ValueError(
                "Quantity must be a positive whole number"
            )

        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                raise ValueError("Quantity must be a valid positive whole number")
            if not value.is_integer():
                raise ValueError(
                    "Quantity must be a whole number. "
                    "Decimal quantities like 0.5 are not allowed"
                )
            raise ValueError(
                "Quantity must be provided as a whole number"
            )

        if isinstance(value, Decimal):
            if not value.is_finite() or value != value.to_integral_value():
                raise ValueError(
                    "Quantity must be a whole number. "
                    "Decimal quantities like 0.5 are not allowed"
                )
            raise ValueError(
                "Quantity must be provided as a whole number"
            )

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("Required field is not provided.")

            if "." in cleaned or "e" in cleaned.lower():
                raise ValueError(
                    "Quantity must be a whole number. "
                    "Decimal quantities like 0.5 are not allowed"
                )

            if not cleaned.isdigit():
                raise ValueError(
                    "Quantity must contain only numbers"
                )

            value = int(cleaned)

        if not isinstance(value, int):
            raise ValueError(
                "Quantity must be a positive whole number"
            )

        if value <= 0:
            raise ValueError(
                "Quantity must be greater than 0"
            )

        if value > 100000:
            raise ValueError(
                "Quantity cannot exceed 100,000"
            )

        return value


class StoreTransferItemCreate(StoreTransferItemBase):
    pass


class StoreTransferItemUpdate(StoreTransferItemBase):
    pass


# ============================================================
# TRANSFER SCHEMAS
# ============================================================

class StoreTransferCreate(BaseModel):
    source_store_id: StrictInt = Field(
        ...,
        gt=0,
        description="Source store ID must be greater than 0",
    )

    destination_store_id: StrictInt = Field(
        ...,
        gt=0,
        description="Destination store ID must be greater than 0",
    )

    items: List[StoreTransferItemCreate] = Field(
        ...,
        min_length=1,
        description="At least one transfer item is required",
    )

    @field_validator("source_store_id", mode="before")
    @classmethod
    def validate_source_store_id_field(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Required field is not provided.")
        return validate_store_id(value, "Source store ID")

    @field_validator("destination_store_id", mode="before")
    @classmethod
    def validate_destination_store_id_field(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Required field is not provided.")
        return validate_store_id(value, "Destination store ID")

    @field_validator("items", mode="before")
    @classmethod
    def validate_items_presence(cls, items):
        if items is None or (isinstance(items, list) and len(items) == 0):
            raise ValueError("Required field is not provided.")
        if not isinstance(items, list):
            raise ValueError("Items must be a list of transfer items")
        return items

    @field_validator("items")
    @classmethod
    def validate_items_list(cls, items: List[StoreTransferItemCreate]):
        if not items:
            raise ValueError("Required field is not provided.")

        seen_product_ids = set()
        for item in items:
            pid = item.product_id
            if pid in seen_product_ids:
                raise ValueError(
                    f"Duplicate product ID {pid} found in transfer items. "
                    "Each product can only appear once per transfer."
                )
            seen_product_ids.add(pid)

        return items

    @model_validator(mode="after")
    def validate_stores(self):
        if self.source_store_id == self.destination_store_id:
            raise ValueError(
                "Source store and destination store must be different"
            )

        return self


class StoreTransferUpdate(BaseModel):
    items: List[StoreTransferItemUpdate] = Field(
        ...,
        min_length=1,
        description="At least one transfer item is required",
    )

    @field_validator("items", mode="before")
    @classmethod
    def validate_items_presence(cls, items):
        if items is None or (isinstance(items, list) and len(items) == 0):
            raise ValueError("Required field is not provided.")
        if not isinstance(items, list):
            raise ValueError("Items must be a list of transfer items")
        return items

    @field_validator("items")
    @classmethod
    def validate_items_list(cls, items: List[StoreTransferItemUpdate]):
        if not items:
            raise ValueError("Required field is not provided.")

        seen_product_ids = set()
        for item in items:
            pid = item.product_id
            if pid in seen_product_ids:
                raise ValueError(
                    f"Duplicate product ID {pid} found in transfer items. "
                    "Each product can only appear once per transfer."
                )
            seen_product_ids.add(pid)

        return items


class StoreTransferApprove(BaseModel):
    approved_by: Optional[StrictInt] = Field(
        default=None,
        ge=1,
        description="Enter the User ID of the person approving this store transfer (leave empty or null to use logged-in user ID). Example: 2.",
        json_schema_extra={"example": 2},
    )

    @field_validator("approved_by", mode="before")
    @classmethod
    def validate_approved_by(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return validate_staff_id(value, "Approved by user ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "approved_by": 2
            }
        }
    )


class StoreTransferReject(BaseModel):
    rejection_reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional reason for rejecting the transfer request",
        json_schema_extra={"example": "Source branch has insufficient stock available"},
    )


# ============================================================
# DISCREPANCY SCHEMAS
# ============================================================

class StoreTransferDiscrepancyItemInput(BaseModel):
    product_id: StrictInt = Field(..., gt=0, description="Product ID being received")
    received_quantity: StrictInt = Field(..., ge=0, description="Quantity received in good sellable condition")
    damaged_quantity: StrictInt = Field(default=0, ge=0, description="Quantity received damaged or defective")
    missing_quantity: StrictInt = Field(default=0, ge=0, description="Quantity missing or lost in transit")
    remarks: Optional[str] = Field(default=None, max_length=255, description="Item-level discrepancy remarks")

    @field_validator("product_id", mode="before")
    @classmethod
    def validate_pid(cls, value):
        return validate_positive_integer_id(value, "Product ID")

    @field_validator("received_quantity", "damaged_quantity", "missing_quantity", mode="before")
    @classmethod
    def validate_quantities(cls, value, info):
        if value is None:
            return 0
        if isinstance(value, bool):
            raise ValueError(f"{info.field_name} must be a whole number")
        if isinstance(value, (float, Decimal)):
            if not math.isclose(float(value), int(value)):
                raise ValueError(f"{info.field_name} must be a whole number")
            value = int(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned.isdigit():
                raise ValueError(f"{info.field_name} must contain only numbers")
            value = int(cleaned)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{info.field_name} must be greater than or equal to 0")
        return value


class StoreTransferDiscrepancyRequest(BaseModel):
    items: List[StoreTransferDiscrepancyItemInput] = Field(
        ...,
        min_length=1,
        description="List of received items with their discrepancy breakdown",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Overall discrepancy notes or remarks",
    )


class StoreTransferDiscrepancyItemResponse(BaseModel):
    product_id: int
    product_name: Optional[str] = None
    sku: Optional[str] = None
    dispatched_quantity: int
    received_quantity: int
    damaged_quantity: int = 0
    missing_quantity: int = 0
    remarks: Optional[str] = None


class StoreTransferDiscrepancyResponse(BaseModel):
    transfer_id: int
    transfer_number: str
    source_store_id: int
    source_store_name: Optional[str] = None
    destination_store_id: int
    destination_store_name: Optional[str] = None
    status: str
    has_discrepancy: bool
    total_dispatched_quantity: int
    total_received_quantity: int
    total_damaged_quantity: int
    total_missing_quantity: int
    discrepancy_notes: Optional[str] = None
    items: List[StoreTransferDiscrepancyItemResponse] = []
    message: str


# ============================================================
# SUMMARY / ANALYTICS SCHEMAS
# ============================================================

class TopStoreStat(BaseModel):
    store_id: int
    store_name: str
    transfer_count: int


class TopProductStat(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    total_quantity: int


class RecentTransferStat(BaseModel):
    id: int
    transfer_number: str
    source_store_name: Optional[str] = None
    destination_store_name: Optional[str] = None
    status: str
    created_at: datetime
    total_items: int


class StoreTransferSummaryResponse(BaseModel):
    total_transfers: int
    pending_transfers: int
    approved_transfers: int
    dispatched_transfers: int
    received_transfers: int
    rejected_transfers: int
    in_transit_transfers: int
    total_units_transferred: int
    top_source_stores: List[TopStoreStat] = []
    top_destination_stores: List[TopStoreStat] = []
    top_transferred_products: List[TopProductStat] = []
    recent_transfers: List[RecentTransferStat] = []


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class StoreTransferItemResponse(BaseModel):
    product_id: int = Field(..., description="Product ID")
    quantity: int = Field(..., description="Quantity transferred")
    product_name: Optional[str] = Field(default=None, description="Product Name")
    sku: Optional[str] = Field(default=None, description="Product SKU")

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if isinstance(value, (Decimal, float)):
            return int(value)
        return value

    model_config = ConfigDict(from_attributes=True)


class StoreTransferResponse(BaseModel):
    id: int = Field(..., description="Transfer ID")
    transfer_number: str = Field(..., description="Transfer reference number")
    source_store_id: int = Field(..., description="Source store ID")
    source_store_name: Optional[str] = Field(default=None, description="Source store name")
    destination_store_id: int = Field(..., description="Destination store ID")
    destination_store_name: Optional[str] = Field(default=None, description="Destination store name")
    status: str = Field(..., description="Transfer status")
    approved_by: Optional[int] = Field(default=None, description="Approver user ID")
    approved_by_name: Optional[str] = Field(default=None, description="Approver user full name")
    created_at: datetime = Field(
        ...,
        description="Creation timestamp",
        json_schema_extra={"example": "2026-10-05T03:57:21.992Z"},
    )
    items: List[StoreTransferItemResponse] = Field(default=[], description="List of transferred items")
    total_items: Optional[int] = Field(default=None, description="Total unique items in transfer")
    total_quantity: Optional[int] = Field(default=None, description="Total units transferred")

    model_config = ConfigDict(from_attributes=True)