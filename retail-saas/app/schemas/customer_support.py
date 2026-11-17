from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReturnItemDetail(BaseModel):
    product_id: Optional[int] = Field(default=None, description="Product ID to return")
    order_item_id: Optional[int] = Field(default=None, description="OrderItem ID if known")
    product_name: Optional[str] = Field(default=None, description="Product name or keyword")
    quantity: int = Field(default=1, ge=1, description="Quantity to return")
    reason: Optional[str] = Field(default=None, description="Item specific return reason")


class CustomerReturnInitiateRequest(BaseModel):
    order_number: str = Field(..., min_length=3, max_length=100, description="Order number to return (e.g. ORD-1001)")
    customer_phone: str = Field(..., min_length=5, max_length=20, description="Customer phone for verification")
    reason: str = Field(..., min_length=3, max_length=200, description="Reason for return (defective, wrong_item, expired, etc.)")
    remarks: Optional[str] = Field(default=None, max_length=500, description="Additional customer remarks")
    refund_preference: Literal["store_credit", "upi", "cash", "original_payment"] = Field(
        default="store_credit", description="Preferred refund method"
    )
    items: Optional[List[ReturnItemDetail]] = Field(
        default=None, description="Specific items to return. If omitted, applies to entire order."
    )


class CustomerReturnResponse(BaseModel):
    return_id: int
    return_number: str
    order_number: str
    status: str
    total_refund_amount: float
    refund_preference: str
    created_at: datetime
    message: str


class CustomerOrderTrackRequest(BaseModel):
    order_number: Optional[str] = Field(default=None, description="Order number (e.g. ORD-1001)")
    customer_phone: Optional[str] = Field(default=None, description="Customer phone number")


class OrderItemSummary(BaseModel):
    product_name: str
    quantity: float
    unit_price: float
    total: float


class CustomerOrderTrackResponse(BaseModel):
    order_id: int
    order_number: str
    status: str
    total_amount: float
    order_date: datetime
    items: List[OrderItemSummary]
    delivery_status: Optional[str] = None
    delivery_partner: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[str] = None
    invoice_pdf_url: Optional[str] = None
    is_return_eligible: bool = False
    status_description: str


class CustomerInvoiceDownloadResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    order_number: str
    total_amount: float
    date: datetime
    pdf_url: str
    download_link: str
    status: str


class CustomerSupportQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Customer question or support message")
    customer_phone: Optional[str] = Field(default=None, max_length=20, description="Customer phone number for context")
    order_number: Optional[str] = Field(default=None, max_length=100, description="Optional active order number")
    session_id: Optional[str] = Field(default=None, max_length=100, description="Web widget session identifier")
    tenant_id: Optional[int] = Field(default=None, description="Tenant organization ID (if multi-tenant widget)")
    store_id: Optional[int] = Field(default=None, description="Store location ID")
    language: Optional[str] = Field(default="mr", description="Language preference: 'mr' (Marathi), 'en' (English), 'hi' (Hindi)")


class CustomerSupportQueryResponse(BaseModel):
    intent: Literal[
        "order_tracking",
        "invoice_download",
        "return_request",
        "faq_store_info",
        "human_handoff",
        "greeting",
        "general",
    ]
    reply: str
    speech_text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    suggested_actions: List[str] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)
