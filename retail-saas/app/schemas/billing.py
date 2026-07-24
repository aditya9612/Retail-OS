from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

VALID_REFUND_METHODS = ["cash", "upi", "store_credit"]
VALID_PAYMENT_MODES = ["cash", "upi", "card", "credit_card", "debit_card", "wallet", "qr"]


class RefundCreate(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    refund_amount: Decimal = Field(gt=0, le=Decimal("999999.99"), description="Refund amount must be greater than 0")
    refund_method: str = Field(description="Must be cash, upi or store_credit")
    reason: Optional[str] = Field(default=None, min_length=3, max_length=500)

    @field_validator("refund_method")
    @classmethod
    def validate_refund_method(cls, v: str) -> str:
        if v not in VALID_REFUND_METHODS:
            raise ValueError(f"refund_method must be one of {VALID_REFUND_METHODS}")
        return v


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
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditNoteCreate(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    refund_amount: Decimal = Field(gt=0, le=Decimal("999999.99"), description="Refund amount must be greater than 0")
    reason: Optional[str] = Field(default=None, min_length=3, max_length=500)


class PaymentSplit(BaseModel):
    payment_mode: str = Field(description="Must be a valid payment mode")
    amount: Decimal = Field(gt=0, le=Decimal("999999.99"), description="Amount must be greater than 0")
    transaction_reference: Optional[str] = Field(default=None, max_length=255)

    @field_validator("payment_mode")
    @classmethod
    def validate_payment_mode(cls, v: str) -> str:
        if v not in VALID_PAYMENT_MODES:
            raise ValueError(f"payment_mode must be one of {VALID_PAYMENT_MODES}")
        return v


class InvoiceCreate(BaseModel):
    store_id: int = Field(gt=0, description="Store ID must be positive")
    customer_id: Optional[int] = Field(default=None, gt=0)
    same_state: bool = True
    payments: list["PaymentSplit"] = Field(default=[], max_length=5)


class ReturnItemRequest(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    product_id: int = Field(gt=0, description="Product ID must be positive")
    return_quantity: Decimal = Field(gt=0, le=Decimal("10000"), description="Return quantity must be greater than 0")
    reason: Optional[str] = Field(default=None, min_length=3, max_length=500)


class ThermalPrintResponse(BaseModel):
    printer_type: str
    encoding: str
    payload: str
    byte_payload: str