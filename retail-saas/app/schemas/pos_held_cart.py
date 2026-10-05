from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class POSHoldCartRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=255, description="Reason or note for holding cart")
    customer_name: Optional[str] = Field(default=None, max_length=100, description="Customer name for held cart")
    customer_phone: Optional[str] = Field(default=None, max_length=20, description="Customer phone for held cart")
    customer_id: Optional[int] = Field(default=None, gt=0, description="Customer ID if registered")


class POSRecallCartRequest(BaseModel):
    force_override: bool = Field(
        default=False,
        description="If True, overwrites active cart even if active cart currently has items",
    )


class POSHeldCartResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    user_id: int
    cashier_name: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    hold_reference: str
    notes: Optional[str] = None
    status: str
    items_count: int
    subtotal: Decimal
    discount_amount: Decimal
    gst_amount: Decimal
    grand_total: Decimal
    same_state: bool
    cart_data: Dict[str, Any]
    held_at: datetime
    recalled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class POSHeldCartListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[POSHeldCartResponse]

    model_config = ConfigDict(from_attributes=True)

