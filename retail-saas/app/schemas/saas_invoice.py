from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SaaSInvoiceResponse(BaseModel):
    id: int
    tenant_id: int
    subscription_id: int
    invoice_number: str
    billing_reason: str
    subtotal: Decimal = Field(default=Decimal("0.00"), examples=[Decimal("999.00")])
    tax_amount: Decimal = Field(default=Decimal("0.00"), examples=[Decimal("179.82")])
    total_amount: Decimal = Field(default=Decimal("0.00"), examples=[Decimal("1178.82")])
    currency: str
    status: str
    due_date: datetime
    paid_at: Optional[datetime] = None
    pdf_url: Optional[str] = None
    notes: Optional[str] = None
    sac_code: Optional[str] = Field(default="998313", description="Services Accounting Code for SaaS (998313)")
    tax_rate: Optional[Decimal] = Field(default=Decimal("18.00"), description="GST rate percentage")
    cgst_amount: Optional[Decimal] = Field(default=Decimal("0.00"), description="Central GST amount (9%)")
    sgst_amount: Optional[Decimal] = Field(default=Decimal("0.00"), description="State GST amount (9%)")
    igst_amount: Optional[Decimal] = Field(default=Decimal("0.00"), description="Integrated GST amount (18%)")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SaaSInvoiceListResponse(BaseModel):
    items: list[SaaSInvoiceResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)
