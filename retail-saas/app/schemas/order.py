from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

VALID_ORDER_TYPES = ["pos", "ecommerce"]
VALID_ORDER_STATUSES = [
    "draft", "confirmed", "processing",
    "shipped", "delivered", "cancelled",
    "returned", "refunded"
]
VALID_PAYMENT_METHODS = ["cash", "upi", "card", "credit_card", "debit_card", "wallet", "qr"]


class OrderItemCreate(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, le=10000, description="Quantity must be between 1 and 10000")
    unit_price: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"))
    discount: Decimal = Field(default=Decimal("0.00"), ge=0, le=Decimal("999999.99"))
    variant: Optional[str] = Field(default=None, max_length=100)


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
    store_id: int = Field(gt=0, description="Store ID must be positive")
    customer_id: Optional[int] = Field(default=None, gt=0)
    order_type: str = Field(default="pos")
    coupon_code: Optional[str] = Field(default=None, min_length=3, max_length=50)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0, le=Decimal("999999.99"))
    delivery_address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1000)
    items: List[OrderItemCreate] = Field(min_length=1, max_length=100, description="Order must have 1 to 100 items")

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        if v not in VALID_ORDER_TYPES:
            raise ValueError(f"order_type must be one of {VALID_ORDER_TYPES}")
        return v

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[OrderItemCreate]) -> List[OrderItemCreate]:
        product_ids = [item.product_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Order cannot have duplicate products")
        return v


class OrderUpdate(BaseModel):
    customer_id: Optional[int] = Field(default=None, gt=0)
    coupon_code: Optional[str] = Field(default=None, min_length=3, max_length=50)
    discount_amount: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999.99"))
    delivery_address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_ORDER_STATUSES:
            raise ValueError(f"status must be one of {VALID_ORDER_STATUSES}")
        return v


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
    order_id: int = Field(gt=0, description="Order ID must be positive")
    payment_method: str = Field(description="Must be a valid payment method")
    amount: Decimal = Field(gt=0, le=Decimal("999999.99"), description="Amount must be greater than 0")
    transaction_id: Optional[str] = Field(default=None, max_length=100)

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        if v not in VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of {VALID_PAYMENT_METHODS}")
        return v


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
    

class OrderTrackingResponse(BaseModel):
    id: int
    order_id: int
    status: str
    remarks: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}
    
    
class OrderStatusUpdateRequest(BaseModel):
    status: str
    remarks: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_ORDER_STATUSES:
            raise ValueError(f"status must be one of {VALID_ORDER_STATUSES}")
        return v
