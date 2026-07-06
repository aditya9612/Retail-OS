from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

VALID_GST_SLABS = [Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28")]


class GstRateCreate(BaseModel):
    hsn_code: str = Field(min_length=4, max_length=8, description="HSN code must be 4 to 8 digits")
    gst_rate: Decimal = Field(ge=0, le=100, description="GST rate must be 0, 5, 12, 18 or 28")

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("HSN code must contain digits only")
        return v

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_slab(cls, v: Decimal) -> Decimal:
        if v not in VALID_GST_SLABS:
            raise ValueError(f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}")
        return v


class GstRateUpdate(BaseModel):
    gst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100, description="GST rate must be 0, 5, 12, 18 or 28")
    status: Optional[bool] = None

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_slab(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v not in VALID_GST_SLABS:
            raise ValueError(f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}")
        return v


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