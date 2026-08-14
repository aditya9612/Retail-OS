from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class SaleItemCreate(BaseModel):
    product_id: int = Field(
        ...,
        gt=0,
        json_schema_extra={
            "example": "string"
        }
    )

    stock: int = Field(
        ...,
        gt=0,
        json_schema_extra={
            "example": "string"
        }
    )

    discount: float = Field(
        ...,
        ge=0,
        json_schema_extra={
            "example": "string"
        }
    )


class SaleCreate(BaseModel):
    store_id: int = Field(
        ...,
        gt=0,
        json_schema_extra={
            "example": "string"
        }
    )

    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        json_schema_extra={
            "example": "string"
        }
    )

    payment_method: str = Field(
        ...,
        min_length=1,
        max_length=30,
        json_schema_extra={
            "example": "string"
        }
    )

    items: List[SaleItemCreate] = Field(
        ...,
        min_length=1
    )


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    discount: float
    tax: float
    total_price: float

    model_config = ConfigDict(
        from_attributes=True
    )


class SaleResponse(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int]
    invoice_number: str
    subtotal: float
    discount: float
    tax: float
    total_amount: float
    payment_method: str
    status: str
    created_at: object
    items: List[SaleItemResponse]

    model_config = ConfigDict(
        from_attributes=True
    )