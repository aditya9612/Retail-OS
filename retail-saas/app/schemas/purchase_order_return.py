from datetime import datetime
from decimal import Decimal

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


class PurchaseOrderReturnCreate(BaseModel):

    purchase_order_id: int = Field(
        gt=0,
        description="Purchase Order ID must be positive",
    )

    reason: str = Field(
        min_length=3,
        max_length=100,
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
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
    def validate_remarks(cls, value: str | None) -> str | None:
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
                "Duplicate Purchase Order Item IDs are not allowed"
            )

        return value


class PurchaseOrderReturnUpdate(BaseModel):

    reason: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None):
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
    def validate_remarks(cls, value: str | None):
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
        if self.reason is None and self.remarks is None:
            raise ValueError(
                "At least one field must be provided for update"
            )

        return self


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
    quantity: int
    unit_price: Decimal
    total: Decimal

    model_config = ConfigDict(
        from_attributes=True
    )


class PurchaseOrderReturnResponse(BaseModel):

    id: int
    tenant_id: int
    purchase_order_id: int
    reason: str
    remarks: str | None
    status: str
    total_amount: Decimal
    created_at: datetime

    items: list[PurchaseOrderReturnItemResponse]

    model_config = ConfigDict(
        from_attributes=True
    )