from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Optional[Decimal] = None
    discount: Decimal = Field(default=Decimal("0.00"))


class CartItemUpdate(BaseModel):
    product_id: int
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None


class CartItemResponse(BaseModel):
    product_id: int
    product_name: str
    sku: str
    hsn_code: Optional[str]
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    gst_rate: Decimal
    gst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal


class CartDiscountApply(BaseModel):
    discount_type: str = Field(description="percentage | fixed | coupon | store_wide")
    value: Decimal = Field(ge=0)
    coupon_code: Optional[str] = None


class CartSummaryResponse(BaseModel):
    store_id: int
    customer_id: Optional[int]
    items: list[CartItemResponse]
    subtotal: Decimal
    discount_amount: Decimal
    gst_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    grand_total: Decimal
    same_state: bool
    coupon_code: Optional[str] = None
