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
    approved_by: StrictInt = Field(
        ...,
        ge=1,
        description="ID of the user/staff member approving the store transfer. Enter an existing User/Staff ID. Example: 5.",
        json_schema_extra={"example": 5},
    )

    @field_validator("approved_by", mode="before")
    @classmethod
    def validate_approved_by(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Required field is not provided.")
        return validate_staff_id(value, "Approved by user ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "approved_by": 5
            }
        }
    )


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class StoreTransferItemResponse(BaseModel):
    product_id: int = Field(..., description="Product ID")
    quantity: int = Field(..., description="Quantity transferred")

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
    destination_store_id: int = Field(..., description="Destination store ID")
    status: str = Field(..., description="Transfer status")
    approved_by: Optional[int] = Field(default=None, description="Approver user ID")
    created_at: datetime = Field(
        ...,
        description="Creation timestamp",
        json_schema_extra={"example": "2026-10-05T03:57:21.992Z"},
    )
    items: List[StoreTransferItemResponse] = Field(default=[], description="List of transferred items")

    model_config = ConfigDict(from_attributes=True)