from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class RefundCreate(BaseModel):
    invoice_id: int
    refund_amount: Decimal = Field(gt=0)
    refund_method: str
    reason: Optional[str] = None


class RefundResponse(BaseModel):
    id: int
    tenant_id: int
    invoice_id: int
    refund_amount: Decimal
    refund_method: str
    status: str
    reason: Optional[str]
    approved_by: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditNoteResponse(BaseModel):
    id: int
    tenant_id: int
    credit_note_no: str
    invoice_id: int
    refund_id: int
    refund_amount: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}