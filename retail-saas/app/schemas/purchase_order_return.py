from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


INVALID_STRING_VALUES = {
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "n/a",
    "na",
    "null value",
}


def validate_text(
    value: str,
    field_name: str,
    min_length: int,
    max_length: int,
) -> str:
    value = value.strip()

    if not value:
        raise ValueError(f"{field_name} cannot be empty")

    if value.lower() in INVALID_STRING_VALUES:
        raise ValueError(f"Invalid {field_name}")

    if len(value) < min_length:
        raise ValueError(
            f"{field_name} must contain at least {min_length} characters"
        )

    if len(value) > max_length:
        raise ValueError(
            f"{field_name} must not exceed {max_length} characters"
        )

    return value


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


class PurchaseOrderReturnCreate(BaseModel):
    purchase_order_id: int = Field(
        gt=0,
        description="Purchase Order ID must be positive",
    )
    reason: str = Field(
        min_length=3,
        max_length=100,
    )
    remarks: Optional[str] = Field(
        default=None,
        max_length=500,
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
        )

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        return validate_text(
            value,
            "Remarks",
            3,
            500,
        )

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
    remarks: Optional[str] = Field(
        default=None,
        max_length=500,
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
        )

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: Optional[str]):
        if value is None:
            return None

        return validate_text(
            value,
            "Remarks",
            3,
            500,
        )

    @model_validator(mode="after")
    def validate_update(self):
        if self.reason is None and self.remarks is None and self.debit_note_number is None and self.items is None:
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
        return validate_text(value, "Rejection reason", 3, 500)


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
    remarks: Optional[str] = None
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