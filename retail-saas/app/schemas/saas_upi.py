from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UPICheckoutPreviewResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    amount: Decimal
    currency: str
    due_date: datetime
    subscription_id: int
    plan_code: str
    plan_name: str
    subscription_status: str
    model_config = ConfigDict(from_attributes=True)


class UPIInitiateResponse(BaseModel):
    reference: str
    amount: Decimal
    currency: str
    upi_vpa: str
    upi_payload: str
    invoice_id: int
    subscription_id: int
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UPIQRCodeResponse(BaseModel):
    reference: str
    upi_payload: str
    qr_image_base64: str
    amount: Decimal
    currency: str
    upi_vpa: str


class UPISubmitRequest(BaseModel):
    reference: str = Field(..., min_length=1, max_length=64)
    utr: str = Field(..., min_length=1, max_length=50)
    payer_vpa: Optional[str] = Field(None, max_length=100)
    proof_image_url: Optional[str] = Field(None, max_length=500)


class UPITransactionResponse(BaseModel):
    id: int
    reference: str
    status: str
    amount: Decimal
    currency: str
    upi_id: str
    payer_vpa: Optional[str] = None
    utr: Optional[str] = None
    invoice_id: int
    subscription_id: int
    tenant_id: int
    proof_image_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UPIAdminTransactionResponse(BaseModel):
    id: int
    reference: str
    status: str
    amount: Decimal
    currency: str
    upi_id: str
    payer_vpa: Optional[str] = None
    utr: Optional[str] = None
    invoice_id: int
    subscription_id: int
    tenant_id: int
    proof_image_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    verified_by_super_admin_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UPITransactionListResponse(BaseModel):
    items: list[UPIAdminTransactionResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    model_config = ConfigDict(from_attributes=True)


class UPIVerifyRequest(BaseModel):
    pass


class UPIRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=5, max_length=255)
