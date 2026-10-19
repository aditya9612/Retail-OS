from datetime import date, datetime
from decimal import Decimal
import re
from typing import Optional

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
    product_id: int = Field(gt=0, description="Product ID must be positive")
    ordered_quantity: Optional[int] = Field(default=None, gt=0, description="Ordered quantity must be greater than 0")
    received_quantity: int = Field(default=1, ge=0, description="Received quantity")
    accepted_quantity: Optional[int] = Field(default=None, ge=0, description="Accepted quantity")
    rejected_quantity: Optional[int] = Field(default=0, ge=0, description="Rejected quantity")
    damage_reason: Optional[str] = Field(default=None, max_length=255)
    unit_cost: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    remarks: Optional[str] = Field(default=None, max_length=500)

    @field_validator("remarks")
    @classmethod
    def validate_item_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)

    @model_validator(mode="after")
    def validate_received_vs_ordered(self) -> "GRNItemCreate":
        if self.ordered_quantity is not None and self.ordered_quantity > 0 and self.received_quantity > self.ordered_quantity:
            raise ValueError(
                f"Received quantity ({self.received_quantity}) cannot be greater than ordered quantity ({self.ordered_quantity})"
            )
        return self


class GRNCreate(BaseModel):
    purchase_order_id: Optional[int] = Field(default=None, gt=0, description="Purchase order ID")
    warehouse_id: Optional[int] = Field(default=None, gt=0, description="Warehouse ID")
    store_id: Optional[int] = Field(default=None, gt=0, description="Store ID")
    invoice_number: Optional[str] = Field(default=None, max_length=100)
    invoice_date: Optional[date] = None
    vehicle_number: Optional[str] = Field(default=None, max_length=50)
    transporter_name: Optional[str] = Field(default=None, max_length=100)
    remarks: Optional[str] = Field(default=None, max_length=1000)
    items: list[GRNItemCreate] = Field(default_factory=list)

    @field_validator("remarks")
    @classmethod
    def validate_root_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)

    @model_validator(mode="after")
    def validate_items_present(self) -> "GRNCreate":
        if not self.purchase_order_id and not self.items:
            raise ValueError("At least one item is required")
        return self


class GRNItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    ordered_quantity: int
    received_quantity: int
    accepted_quantity: Optional[int] = None
    rejected_quantity: Optional[int] = 0
    damage_reason: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = None
    remarks: Optional[str] = None


class GRNResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    purchase_order_id: Optional[int] = None
    purchase_order_number: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    grn_number: str
    status: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    remarks: Optional[str] = None
    rejection_reason: Optional[str] = None
    received_at: Optional[datetime] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    received_by_id: Optional[int] = None
    received_by_name: Optional[str] = None

    # Aggregated metrics
    total_items_count: int = 0
    total_ordered_quantity: int = 0
    total_received_quantity: int = 0
    total_accepted_quantity: int = 0
    total_rejected_quantity: int = 0
    total_cost_value: Decimal = Decimal("0.00")

    created_at: datetime
    updated_at: datetime

    items: list[GRNItemResponse] = []


class GRNItemQCUpdate(BaseModel):
    item_id: int = Field(gt=0, description="GRN item ID")
    accepted_quantity: int = Field(ge=0, description="Quantity accepted into stock")
    rejected_quantity: int = Field(default=0, ge=0, description="Quantity rejected / damaged")
    damage_reason: Optional[str] = Field(default=None, max_length=255)
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    remarks: Optional[str] = Field(default=None, max_length=500)


class GRNQualityCheckRequest(BaseModel):
    items: list[GRNItemQCUpdate] = Field(..., min_length=1)
    remarks: Optional[str] = Field(default=None, max_length=1000)


class GRNRejectRequest(BaseModel):
    reason: Optional[str] = Field(default="Shipment rejected during receipt", max_length=1000)


class GRNHistoryEvent(BaseModel):
    event: str
    timestamp: datetime
    performed_by: Optional[str] = None
    details: Optional[str] = None


class GRNHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grn_id: int
    grn_number: str
    status: str
    created_at: datetime
    received_at: Optional[datetime] = None
    updated_at: datetime
    created_by_name: Optional[str] = None
    received_by_name: Optional[str] = None
    rejection_reason: Optional[str] = None
    timeline: list[GRNHistoryEvent] = []


class GRNStatsResponse(BaseModel):
    total_grns: int
    pending_grns: int
    received_grns: int
    rejected_grns: int
    received_today: int
    total_inward_value: Decimal
    recent_grns: list[GRNResponse] = []


class GRNPrintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grn_number: str
    tenant_id: int
    purchase_order_id: Optional[int] = None
    purchase_order_number: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    status: str
    remarks: Optional[str] = None
    rejection_reason: Optional[str] = None
    received_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    received_by_name: Optional[str] = None

    total_items_count: int = 0
    total_ordered_quantity: int = 0
    total_received_quantity: int = 0
    total_accepted_quantity: int = 0
    total_rejected_quantity: int = 0
    total_cost_value: Decimal = Decimal("0.00")

    created_at: datetime
    updated_at: datetime
    items: list[GRNItemResponse] = []


class GRNDeleteResponse(BaseModel):
    success: bool = True
    message: str
    id: int

