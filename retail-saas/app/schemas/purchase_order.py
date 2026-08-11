from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
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

    unit_price: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Unit price must be greater than zero",
    )


class PurchaseOrderCreate(BaseModel):
    supplier_id: int = Field(
        gt=0,
        description="Supplier ID must be positive",
    )

    store_id: int = Field(
        gt=0,
        description="Store ID must be positive",
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )

    items: list[PurchaseOrderItemCreate]

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

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )


class PurchaseOrderReceive(BaseModel):
    remarks: str | None = Field(
        default=None,
        max_length=500,
    )


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
    product_id: int
    quantity: int
    unit_price: Decimal
    total: Decimal

    model_config = {
        "from_attributes": True,
    }


class PurchaseOrderResponse(BaseModel):
    id: int
    tenant_id: int
    supplier_id: int
    store_id: int
    po_number: str
    status: str
    total_amount: Decimal
    remarks: str | None
    created_at: datetime

    items: list[PurchaseOrderItemResponse]

    model_config = {
        "from_attributes": True,
    }