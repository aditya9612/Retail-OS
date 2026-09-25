from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator


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
        if isinstance(value, bool):
            raise ValueError(
                "Product ID must be a positive whole number"
            )

        if isinstance(value, (float, Decimal)):
            if not value.is_integer():
                raise ValueError(
                    "Product ID must be a whole number"
                )
            raise ValueError(
                "Product ID must be provided as a whole number"
            )

        if isinstance(value, str):
            value = value.strip()

            if not value:
                raise ValueError("Product ID is required")

            if not value.isdigit():
                raise ValueError(
                    "Product ID must contain only numbers"
                )

            value = int(value)

        if not isinstance(value, int):
            raise ValueError(
                "Product ID must be a positive whole number"
            )

        if value <= 0:
            raise ValueError(
                "Product ID must be greater than 0"
            )

        return value

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if isinstance(value, bool):
            raise ValueError(
                "Quantity must be a positive whole number"
            )

        if isinstance(value, (float, Decimal)):
            if not value.is_integer():
                raise ValueError(
                    "Quantity must be a whole number. "
                    "Decimal quantities like 0.5 are not allowed"
                )

        if isinstance(value, str):
            value = value.strip()

            if not value:
                raise ValueError("Quantity is required")

            try:
                number = Decimal(value)
            except Exception:
                raise ValueError(
                    "Quantity must contain only numbers"
                )

            if not number.is_integer():
                raise ValueError(
                    "Quantity must be a whole number. "
                    "Decimal quantities like 0.5 are not allowed"
                )

            value = int(number)

        return value


class StoreTransferItemCreate(StoreTransferItemBase):
    pass


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

    @model_validator(mode="after")
    def validate_stores(self):
        if self.source_store_id == self.destination_store_id:
            raise ValueError(
                "Source store and destination store must be different"
            )

        return self


class StoreTransferItemUpdate(StoreTransferItemBase):
    pass


class StoreTransferUpdate(BaseModel):
    items: List[StoreTransferItemUpdate] = Field(
        ...,
        min_length=1,
        description="At least one transfer item is required",
    )


class StoreTransferApprove(BaseModel):
    approved_by: int | None = Field(default=None, gt=0, description="User ID approving the transfer")


class StoreTransferItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int = Field(gt=0)

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if isinstance(value, Decimal):
            if value != value.to_integral_value():
                raise ValueError("Quantity must be a whole number")
            return int(value)

        return value

    class Config:
        from_attributes = True

class StoreTransferResponse(BaseModel):
    id: int
    transfer_number: str
    source_store_id: int
    destination_store_id: int
    status: str
    approved_by: int | None
    items: List[StoreTransferItemResponse]

    class Config:
        from_attributes = True