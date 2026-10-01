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
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    status: str
    due_date: datetime
    paid_at: Optional[datetime] = None
    pdf_url: Optional[str] = None
    notes: Optional[str] = None
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
