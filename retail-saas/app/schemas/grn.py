from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DISALLOWED_REMARKS_PLACEHOLDERS = {
    "string",
    "test",
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "unknown",
    "placeholder",
    "dummy",
    "sample",
    "remarks",
}


def validate_grn_remarks(value: str | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Remarks must be a string")

    v = value.strip()
    if not v:
        raise ValueError("Remarks cannot be empty")

    if v.lower() in DISALLOWED_REMARKS_PLACEHOLDERS:
        raise ValueError("Please provide a valid remarks")

    if len(v) < 3 or len(v) > 500:
        raise ValueError("Remarks must be between 3 and 500 characters")

    if v.isdigit():
        raise ValueError("Remarks cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Remarks must contain at least one alphabetic character")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError("Remarks cannot consist of repeating characters")

    return v


class GRNItemCreate(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be greater than 0")
    ordered_quantity: int = Field(gt=0, description="Ordered quantity must be greater than 0")
    received_quantity: int = Field(ge=0, description="Received quantity must be greater than or equal to 0")
    remarks: str | None = None

    @field_validator("remarks")
    @classmethod
    def validate_item_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)

    @model_validator(mode="after")
    def validate_received_vs_ordered(self) -> "GRNItemCreate":
        if self.received_quantity > self.ordered_quantity:
            raise ValueError(
                f"Received quantity ({self.received_quantity}) cannot be greater than ordered quantity ({self.ordered_quantity})"
            )
        return self


class GRNCreate(BaseModel):
    purchase_order_id: int | None = Field(
        default=None,
        gt=0,
        description="Purchase order ID must be greater than 0",
    )
    warehouse_id: int | None = Field(
        default=None,
        gt=0,
        description="Warehouse ID must be greater than 0",
    )
    remarks: str | None = None
    items: list[GRNItemCreate] = Field(
        min_length=1,
        description="At least one item is required",
    )

    @field_validator("remarks")
    @classmethod
    def validate_root_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)


class GRNItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    ordered_quantity: int
    received_quantity: int
    remarks: str | None


class GRNResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    purchase_order_id: int | None
    warehouse_id: int | None
    grn_number: str
    status: str
    remarks: str | None
    received_at: datetime | None
    created_at: datetime
    updated_at: datetime

    items: list[GRNItemResponse] = []


class GRNHistoryResponse(BaseModel):
    grn_id: int
    grn_number: str
    status: str
    created_at: datetime
    received_at: datetime | None
    updated_at: datetime


class GRNPrintResponse(BaseModel):
    id: int
    grn_number: str
    tenant_id: int
    purchase_order_id: int | None
    warehouse_id: int | None
    status: str
    remarks: str | None
    received_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[GRNItemResponse]
