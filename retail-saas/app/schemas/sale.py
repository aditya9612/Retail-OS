from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class SaleItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    stock: int = Field(..., gt=0)
    discount: float = Field(default=0.0, ge=0)


class SaleCreate(BaseModel):
    store_id: int = Field(..., gt=0)
    customer_id: Optional[int] = Field(default=None, gt=0)
    payment_method: str = Field(default="cash", min_length=1, max_length=30)
    items: List[SaleItemCreate] = Field(..., min_length=1)


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    discount: float = 0.0
    tax: float = 0.0
    total_price: float

    model_config = ConfigDict(
        from_attributes=True
    )


class SaleResponse(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int] = None
    invoice_number: str
    subtotal: float
    discount: float = 0.0
    tax: float = 0.0
    total_amount: float
    payment_method: str
    status: str
    created_at: datetime
    items: List[SaleItemResponse] = []

    model_config = ConfigDict(
        from_attributes=True
    )