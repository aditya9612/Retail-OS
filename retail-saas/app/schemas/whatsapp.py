from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
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

    # Conversational AI Ordering & Payments
    ai_ordering_enabled: bool = Field(default=True, description="Enable AI conversational ordering via WhatsApp")
    ai_ocr_grocery_enabled: bool = Field(default=True, description="Enable handwritten grocery list OCR to cart/order")
    ai_khata_reminders_enabled: bool = Field(default=True, description="Enable AI smart Khata (credit) recovery reminders")
    khata_min_balance: Decimal = Field(default=Decimal("100.00"), description="Minimum credit balance threshold to trigger reminders")

    upi_vpa: Optional[str] = Field(default=None, max_length=100, description="Store UPI ID for receiving payments (e.g. store@upi)")
    upi_payee_name: Optional[str] = Field(default=None, max_length=100, description="Merchant / Store Name shown on UPI apps")
    ai_welcome_message: Optional[str] = Field(default=None, description="Custom greeting / catalog message sent to customers")


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
    ai_ordering_enabled: Optional[bool] = None
    ai_ocr_grocery_enabled: Optional[bool] = None
    ai_khata_reminders_enabled: Optional[bool] = None
    khata_min_balance: Optional[Decimal] = None
    upi_vpa: Optional[str] = None
    upi_payee_name: Optional[str] = None
    ai_welcome_message: Optional[str] = None


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


# ==============================================================================
# 1. OCR HANDWRITTEN GROCERY LIST SCHEMAS
# ==============================================================================

class ExtractedGroceryItem(BaseModel):
    raw_text: str = Field(..., description="Raw text snippet read from handwritten list")
    item_name: str = Field(..., description="Normalized item name (e.g. बासमती तांदूळ, साखर)")
    quantity: float = Field(default=1.0, description="Requested quantity number (supports decimals like 0.5, 1.5)")
    unit: str = Field(default="pcs", description="Unit of measurement (kg, g, l, ml, pcs, pack)")
    confidence: float = Field(default=0.9, description="Recognition confidence score")


class MappedOrderItemDetail(BaseModel):
    product_id: int
    product_name: str
    sku: str
    quantity: float
    unit: str
    unit_price: float
    tax_amount: float
    total_amount: float


class HandwrittenGroceryOcrRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded photo of the handwritten grocery list")
    mime_type: str = Field(default="image/jpeg", description="MIME type (image/jpeg, image/png, image/webp)")
    recipient_phone: Optional[str] = Field(default=None, description="Customer phone number to link cart/order")
    sender_name: Optional[str] = Field(default=None, description="Customer name if known")
    auto_create_order: bool = Field(default=True, description="Whether to automatically create an order in Retail-OS")
    store_id: Optional[int] = Field(default=None, description="Target store outlet ID")


class HandwrittenGroceryOcrResponse(BaseModel):
    status: str
    extracted_items: List[ExtractedGroceryItem]
    matched_items: List[MappedOrderItemDetail]
    unmatched_items: List[str]
    order_id: Optional[int] = None
    order_number: Optional[str] = None
    subtotal: float
    tax_amount: float
    total_amount: float
    upi_payment_link: Optional[str] = None
    reply_message: str


# ==============================================================================
# 2. CONVERSATIONAL ORDERING SCHEMAS
# ==============================================================================

class WhatsAppChatOrderRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20, description="Customer phone number")
    message: str = Field(..., min_length=1, max_length=2000, description="Customer grocery order text in Marathi/English")
    sender_name: Optional[str] = Field(default=None, description="Customer display name")
    store_id: Optional[int] = Field(default=None, description="Store ID (optional)")


class WhatsAppChatOrderResponse(BaseModel):
    status: str
    intent: str
    order_id: Optional[int] = None
    order_number: Optional[str] = None
    total_amount: Optional[float] = None
    upi_link: Optional[str] = None
    reply: str


# ==============================================================================
# 3. SMART KHATA (उधारी) RECOVERY SCHEMAS
# ==============================================================================

class KhataPendingCustomerItem(BaseModel):
    customer_id: int
    customer_name: str
    phone: str
    outstanding_balance: float
    credit_limit: float
    total_spend: float
    last_reminder_at: Optional[datetime] = None
    last_promised_date: Optional[date] = None
    recovery_status: str # pending, reminder_sent, promised, paid, disputed


class KhataReminderRequest(BaseModel):
    customer_id: Optional[int] = Field(default=None, description="Optional customer ID override")
    custom_note: Optional[str] = Field(default=None, description="Optional custom note to include in reminder")


class KhataReminderBroadcastRequest(BaseModel):
    min_balance: float = Field(default=100.0, ge=1.0, description="Minimum overdue balance threshold")
    store_id: Optional[int] = Field(default=None, description="Optional store filter")


class KhataProcessReplyRequest(BaseModel):
    customer_id: int = Field(..., description="Customer ID")
    reply_message: str = Field(..., description="Customer's WhatsApp reply message (e.g. 'मी उद्या देतो', 'after 2 days')")


class KhataFollowupResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: Optional[int] = None
    customer_id: int
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    outstanding_amount: float
    reminder_sent_at: datetime
    reminder_message: Optional[str] = None
    customer_reply: Optional[str] = None
    detected_intent: Optional[str] = None
    promised_date: Optional[date] = None
    status: str
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KhataFollowupListResponse(BaseModel):
    items: List[KhataFollowupResponse]
    total: int
