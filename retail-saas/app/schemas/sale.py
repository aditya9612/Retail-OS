from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class SaleItemCreate(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: Optional[int] = Field(default=None, gt=0)
    stock: Optional[int] = Field(default=None, gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    tax_rate: Optional[float] = Field(default=0.0, ge=0)
    tax_amount: Optional[float] = Field(default=0.0, ge=0)
    discount: float = Field(default=0.0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def reconcile_quantity(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("quantity") is None and data.get("stock") is not None:
                data["quantity"] = data["stock"]
            elif data.get("stock") is None and data.get("quantity") is not None:
                data["stock"] = data["quantity"]
        return data


class SaleCreate(BaseModel):
    store_id: int = Field(..., gt=0)
    sale_number: Optional[str] = Field(default=None, max_length=50)
    invoice_number: Optional[str] = Field(default=None, max_length=50)
    customer_id: Optional[int] = Field(default=None, gt=0)
    payment_method: str = Field(default="cash", min_length=1, max_length=50)
    payment_status: str = Field(default="paid", min_length=1, max_length=50)
    items: List[SaleItemCreate] = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def reconcile_sale_number(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("sale_number") and data.get("invoice_number"):
                data["sale_number"] = data["invoice_number"]
            elif not data.get("invoice_number") and data.get("sale_number"):
                data["invoice_number"] = data["sale_number"]
        return data


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total_price: float
    discount: float = 0.0
    tax: float = 0.0

    model_config = ConfigDict(
        from_attributes=True
    )


class SaleResponse(BaseModel):
    id: int
    store_id: int
    tenant_id: Optional[int] = None
    sale_number: Optional[str] = None
    invoice_number: str
    subtotal: float
    tax_amount: Optional[float] = 0.0
    total_amount: float
    payment_method: str
    payment_status: Optional[str] = "paid"
    status: str
    discount: float = 0.0
    tax: float = 0.0
    customer_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[SaleItemResponse] = []

    model_config = ConfigDict(
        from_attributes=True
    )