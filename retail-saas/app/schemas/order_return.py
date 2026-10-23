import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_RETURN_STATUSES = [
    "requested",
    "approved",
    "rejected",
    "completed",
]

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

    remarks: str | None = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Return remarks are optional (3-500 characters if provided)",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return validate_return_text(value, "Reason", min_length=3, max_length=100, required=True)

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: str | None) -> str | None:
        return validate_return_text(value, "Remarks", min_length=3, max_length=500, required=False)
    

class OrderReturnUpdate(BaseModel):
    reason: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Return reason must be 3-100 characters",
    )

    remarks: str | None = Field(
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
    reason: str
    remarks: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }