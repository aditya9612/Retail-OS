from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: Optional[Decimal] = None
    discount: Decimal = Field(default=Decimal("0.00"))
    variant: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    variant: Optional[str]

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    order_type: str = "pos"
    coupon_code: Optional[str] = None
    discount_amount: Decimal = Field(default=Decimal("0.00"))
    delivery_address: Optional[str] = None
    notes: Optional[str] = None
    items: List[OrderItemCreate] = []


class OrderUpdate(BaseModel):
    customer_id: Optional[int] = None
    coupon_code: Optional[str] = None
    discount_amount: Optional[Decimal] = None
    delivery_address: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    customer_id: Optional[int]
    order_number: str
    order_type: str
    status: str
    coupon_code: Optional[str]
    discount_amount: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    delivery_address: Optional[str]
    delivery_status: Optional[str]
    notes: Optional[str]
    items: List[OrderItemResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    invoice_number: str
    status: str
    subtotal: Decimal
    discount_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    pdf_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):
    order_id: int
    payment_method: str
    amount: Decimal
    transaction_id: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    payment_method: str
    status: str
    amount: Decimal
    transaction_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
