from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class WhatsAppSettingBase(BaseModel):
    phone_number_id: Optional[str] = Field(default=None, max_length=50, description="Meta Phone Number ID")
    business_account_id: Optional[str] = Field(default=None, max_length=50, description="Meta WhatsApp Business Account ID (WABA)")
    is_enabled: bool = Field(default=True, description="Enable or disable WhatsApp messaging")
    auto_send_invoice: bool = Field(default=True, description="Auto-send invoice PDF on checkout")
    auto_send_order_confirm: bool = Field(default=True, description="Auto-send order confirmation on placement")
    template_invoice: str = Field(default="pos_invoice_receipt", max_length=100)
    template_order_confirm: str = Field(default="order_confirmation", max_length=100)
    template_language: str = Field(default="en_US", max_length=20)
    webhook_verify_token: Optional[str] = Field(default=None, max_length=100)


class WhatsAppSettingUpdate(BaseModel):
    phone_number_id: Optional[str] = None
    business_account_id: Optional[str] = None
    access_token: Optional[str] = Field(default=None, description="Meta Cloud API System User Access Token")
    is_enabled: Optional[bool] = None
    auto_send_invoice: Optional[bool] = None
    auto_send_order_confirm: Optional[bool] = None
    template_invoice: Optional[str] = None
    template_order_confirm: Optional[str] = None
    template_language: Optional[str] = None
    webhook_verify_token: Optional[str] = None


class WhatsAppSettingResponse(WhatsAppSettingBase):
    id: int
    tenant_id: int
    store_id: Optional[int] = None
    has_access_token: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WhatsAppSendInvoiceRequest(BaseModel):
    recipient_phone: Optional[str] = Field(
        default=None,
        min_length=5,
        max_length=20,
        description="Override customer phone number. If omitted, uses invoice customer phone.",
    )
    custom_message: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional custom text note included with invoice",
    )


class WhatsAppSendCustomRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20, description="Recipient phone number (e.g. 9876543210 or +919876543210)")
    message: str = Field(..., min_length=1, max_length=2000, description="Text message content")


class WhatsAppTestRequest(BaseModel):
    recipient_phone: str = Field(..., min_length=5, max_length=20, description="Test recipient phone number")
    template_name: Optional[str] = Field(default=None, description="Optional approved Meta template name to test")


class WhatsAppLogResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: Optional[int] = None
    recipient_phone: str
    message_type: str
    template_name: Optional[str] = None
    meta_message_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    invoice_id: Optional[int] = None
    order_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppLogListResponse(BaseModel):
    items: List[WhatsAppLogResponse]
    total: int
    page: int
    page_size: int

