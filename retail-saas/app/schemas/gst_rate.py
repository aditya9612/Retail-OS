from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class GstRateCreate(BaseModel):
    hsn_code: str = Field(max_length=20)
    gst_rate: Decimal = Field(ge=0, le=100)


class GstRateUpdate(BaseModel):
    gst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    status: Optional[bool] = None


class GstRateResponse(BaseModel):
    id: int
    tenant_id: int
    hsn_code: str
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    status: bool
    created_at: datetime

    model_config = {"from_attributes": True}
