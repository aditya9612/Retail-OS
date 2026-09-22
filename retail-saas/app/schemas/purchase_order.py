from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class PurchaseOrderItemCreate(BaseModel):
    product_id: int = Field(
        gt=0,
        description="Product ID must be positive",
    )

    quantity: int = Field(
        gt=0,
        le=100000,
        description="Quantity must be between 1 and 100000",
    )

    unit_cost: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        description="Unit cost must be greater than zero",
    )

    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        description="Unit price alias for unit_cost",
    )

    @model_validator(mode="before")
    @classmethod
    def reconcile_unit_cost(cls, data):
        if isinstance(data, dict):
            if data.get("unit_cost") is None and data.get("unit_price") is not None:
                data["unit_cost"] = data["unit_price"]
            elif data.get("unit_cost") is not None and data.get("unit_price") is None:
                data["unit_price"] = data["unit_cost"]
        return data


class PurchaseOrderCreate(BaseModel):
    supplier_id: int = Field(
        gt=0,
        description="Supplier ID must be positive",
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Store ID (optional)",
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Notes for the purchase order",
    )

    remarks: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Alias for notes",
    )

    expected_delivery_date: Optional[datetime] = Field(
        default=None,
        description="Expected delivery date",
    )

    items: list[PurchaseOrderItemCreate]

    @model_validator(mode="before")
    @classmethod
    def reconcile_notes(cls, data):
        if isinstance(data, dict):
            if data.get("notes") is None and data.get("remarks") is not None:
                data["notes"] = data["remarks"]
            elif data.get("notes") is not None and data.get("remarks") is None:
                data["remarks"] = data["notes"]
        return data

    @field_validator("items")
    @classmethod
    def validate_items(cls, value):
        if not value:
            raise ValueError(
                "Purchase order must contain at least one item"
            )
        return value


class PurchaseOrderUpdate(BaseModel):
    supplier_id: int | None = Field(
        default=None,
        gt=0,
    )

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    notes: str | None = Field(
        default=None,
        max_length=500,
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )

    expected_delivery_date: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def reconcile_notes(cls, data):
        if isinstance(data, dict):
            if data.get("notes") is None and data.get("remarks") is not None:
                data["notes"] = data["remarks"]
            elif data.get("notes") is not None and data.get("remarks") is None:
                data["remarks"] = data["notes"]
        return data


class PurchaseOrderReceive(BaseModel):
    remarks: str | None = Field(
        default=None,
        max_length=500,
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="before")
    @classmethod
    def reconcile_notes(cls, data):
        if isinstance(data, dict):
            if data.get("notes") is None and data.get("remarks") is not None:
                data["notes"] = data["remarks"]
            elif data.get("notes") is not None and data.get("remarks") is None:
                data["remarks"] = data["notes"]
        return data


class PurchaseOrderStatusUpdate(BaseModel):
    status: str = Field(
        description="Purchase order status",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        allowed = {
            "draft",
            "approved",
            "received",
            "cancelled",
        }

        if value not in allowed:
            raise ValueError(
                "Status must be draft, approved, received or cancelled"
            )

        return value


class PurchaseOrderItemResponse(BaseModel):
    id: int
    po_id: Optional[int] = None
    purchase_order_id: Optional[int] = None
    product_id: int
    quantity: int
    unit_cost: Decimal = Decimal("0.00")
    unit_price: Optional[Decimal] = None
    total_cost: Decimal = Decimal("0.00")
    total: Optional[Decimal] = None
    received_quantity: int = 0

    @model_validator(mode="after")
    def sync_aliases(self):
        if self.po_id is not None and self.purchase_order_id is None:
            self.purchase_order_id = self.po_id
        if self.unit_cost is not None and self.unit_price is None:
            self.unit_price = self.unit_cost
        if self.total_cost is not None and self.total is None:
            self.total = self.total_cost
        return self

    model_config = {
        "from_attributes": True,
    }


class PurchaseOrderResponse(BaseModel):
    id: int
    tenant_id: int
    supplier_id: int
    store_id: Optional[int] = None
    order_number: str
    po_number: Optional[str] = None
    status: str
    total_amount: Decimal
    notes: Optional[str] = None
    remarks: Optional[str] = None
    expected_delivery_date: Optional[datetime] = None
    created_at: datetime

    items: list[PurchaseOrderItemResponse] = []

    @model_validator(mode="after")
    def sync_aliases(self):
        if self.order_number and not self.po_number:
            self.po_number = self.order_number
        if self.notes is not None and self.remarks is None:
            self.remarks = self.notes
        return self

    model_config = {
        "from_attributes": True,
    }