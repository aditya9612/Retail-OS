
import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator

VALID_REFUND_METHODS = ["cash", "upi", "store_credit"]
VALID_PAYMENT_MODES = [
    "cash",
    "upi",
    "card",
    "credit_card",
    "debit_card",
    "wallet",
    "qr",
]

DISALLOWED_REFUND_PLACEHOLDERS = {
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "sample",
    "dummy",
    "temp",
    "n/a",
    "na",
    "null value",
    "unknown",
    "placeholder",
    "reason",
}


class InvoiceThermalMode(str, Enum):
    preview = "preview"
    view = "view"
    download = "download"
    pdf = "pdf"
    html = "html"
    json = "json"
    text = "text"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class RefundThermalMode(str, Enum):
    preview = "preview"
    view = "view"
    download = "download"
    pdf = "pdf"
    html = "html"
    json = "json"
    text = "text"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class CreditNoteThermalMode(str, Enum):
    preview = "preview"
    view = "view"
    download = "download"
    pdf = "pdf"
    html = "html"
    json = "json"
    text = "text"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class RefundReceiptPdfMode(str, Enum):
    download = "download"
    preview = "preview"
    view = "view"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class InvoiceThermalResponse(BaseModel):
    success: bool = True
    message: str = "Invoice thermal receipt generated successfully"
    invoice_id: int
    invoice_number: str
    store_name: str
    grand_total: Decimal
    is_reprint: bool = False
    text_payload: str
    html: str


class InvoiceReprintRequest(BaseModel):
    printer_type: str = Field(default="generic", min_length=1, max_length=50)
    mode: Optional[InvoiceThermalMode] = Field(
        default=None,
        description="Optional thermal output mode: preview, view, download, pdf, html, json, text",
    )


    @field_validator("printer_type", mode="before")
    @classmethod
    def validate_printer_type(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("printer_type must be a string")
        value = value.strip().lower()
        if value not in {"generic", "epson", "tvs"}:
            raise ValueError(
                "printer_type must be one of: generic, epson, tvs"
            )
        return value


class InvoiceVoidRequest(BaseModel):
    reason: Optional[str] = Field(
        default="Customer cancelled at counter",
        min_length=3,
        max_length=500,
        description="Reason for voiding the invoice",
    )


class InvoicePdfStatusResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    status: str
    pdf_url: Optional[str] = None


class RefundCreate(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    refund_amount: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Refund amount must be greater than 0",
    )
    refund_method: str = Field(description="Must be cash, upi or store_credit")
    reason: Optional[str] = Field(default=None, min_length=3, max_length=500)
    approved_by: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("approved_by", "approver_id"),
        description="Approver user ID",
    )

    @field_validator("refund_method")
    @classmethod
    def validate_refund_method(cls, v: str) -> str:
        if v not in VALID_REFUND_METHODS:
            raise ValueError(
                f"refund_method must be one of {VALID_REFUND_METHODS}"
            )
        return v

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Reason must be a string")
        v = v.strip()
        if not v:
            return None
        if len(v) < 3 or len(v) > 500:
            raise ValueError(
                "Reason must be between 3 and 500 characters"
            )

        clean_norm = re.sub(r"[^a-zA-Z]", "", v.lower())
        if v.lower() in DISALLOWED_REFUND_PLACEHOLDERS or clean_norm in DISALLOWED_REFUND_PLACEHOLDERS:
            raise ValueError("Please provide a valid refund reason")

        if v.isdigit():
            raise ValueError("Reason cannot contain only numbers")

        alpha_chars = [c.lower() for c in v if c.isalpha()]
        if len(alpha_chars) < 3:
            raise ValueError("Reason must contain at least 3 alphabetic letters")

        if len(set(alpha_chars)) < 2:
            raise ValueError("Reason cannot consist of repetitive characters")

        if re.search(r"[-+*/=_./\\|@#$%^&*!~`?]{2,}", v):
            raise ValueError("Reason cannot contain consecutive special characters")

        if not re.fullmatch(r"[A-Za-z0-9\s,./#&'()\-:;!?]+", v):
            raise ValueError("Reason contains invalid characters")

        return v

    @field_validator("approved_by", mode="before")
    @classmethod
    def validate_approved_by(cls, v):
        if v is None or v == "":
            return None
        try:
            val = int(v)
            if val <= 0:
                raise ValueError("approved_by must be a positive integer")
            return val
        except (ValueError, TypeError):
            raise ValueError("approved_by must be a valid user ID integer")


class RefundRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500, description="Reason for rejecting the refund request")


class RefundResponse(BaseModel):
    id: int
    tenant_id: int
    invoice_id: int
    refund_amount: Decimal
    refund_method: str
    status: str
    reason: Optional[str] = None
    approved_by: Optional[int] = None
    created_at: datetime
    invoice_number: Optional[str] = None
    credit_note_id: Optional[int] = None
    credit_note_no: Optional[str] = None
    store_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    model_config = {"from_attributes": True}


class RefundThermalResponse(BaseModel):
    success: bool = True
    message: str = "Refund receipt voucher generated successfully"
    refund_id: int
    invoice_id: int
    invoice_number: str
    credit_note_no: Optional[str] = None
    refund_amount: Decimal
    refund_method: str
    status: str
    reason: Optional[str] = None
    customer_name: str
    customer_phone: str
    store_name: str
    approved_by_name: str
    created_at: datetime
    thermal_text: str
    html: Optional[str] = None

    model_config = {"from_attributes": True}


RefundReceiptResponse = RefundThermalResponse


class CreditNoteResponse(BaseModel):
    id: int
    tenant_id: int
    credit_note_no: str
    invoice_id: int
    refund_id: int
    refund_amount: Decimal
    balance_amount: Optional[Decimal] = Decimal("0.00")
    status: Optional[str] = "issued"
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    invoice_number: Optional[str] = None
    store_id: Optional[int] = None
    valid_until: Optional[datetime] = None
    is_expired: Optional[bool] = False
    notes: Optional[str] = None
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditNoteCreate(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    refund_amount: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Refund amount must be greater than 0",
    )
    reason: Optional[str] = Field(default=None, min_length=3, max_length=500)
    refund_method: Optional[str] = Field(default=None, description="Refund method: store_credit, cash, upi, bank_transfer")
    valid_days: Optional[int] = Field(default=90, ge=1, le=365, description="Validity period in days (default: 90)")
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            v = v.strip()
            if len(v) < 3:
                raise ValueError(
                    "Reason must contain at least 3 non-whitespace characters"
                )
            if len(v) > 500:
                raise ValueError("Reason cannot exceed 500 characters")
        return v


class CreditNoteValidateRequest(BaseModel):
    credit_note_no: str = Field(min_length=1, max_length=50, description="Credit note number (e.g. CN-2026-000001)")
    bill_amount: Optional[Decimal] = Field(default=None, gt=0, description="Current bill total to compute applicable deduction")


class CreditNoteValidateResponse(BaseModel):
    valid: bool
    credit_note_id: int
    credit_note_no: str
    status: str
    total_amount: Decimal
    balance_amount: Decimal
    applicable_amount: Decimal
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    valid_until: Optional[datetime] = None
    is_expired: bool = False
    message: str


class CreditNoteRedeemRequest(BaseModel):
    credit_note_no: str = Field(min_length=1, max_length=50, description="Credit note number to redeem")
    amount_to_redeem: Decimal = Field(gt=0, le=Decimal("999999.99"), description="Amount to deduct from credit note balance")
    invoice_id: Optional[int] = Field(default=None, gt=0, description="Invoice ID where credit note is being applied")
    order_id: Optional[int] = Field(default=None, gt=0, description="Order ID where credit note is being applied")
    notes: Optional[str] = Field(default=None, max_length=255, description="Optional redemption notes")


class CreditNoteRedeemResponse(BaseModel):
    success: bool
    credit_note_id: int
    credit_note_no: str
    amount_redeemed: Decimal
    remaining_balance: Decimal
    status: str
    redemption_id: int
    message: str


class CreditNoteThermalResponse(BaseModel):
    success: bool = True
    message: str = "Credit note thermal receipt generated successfully"
    credit_note_id: int
    credit_note_no: str
    invoice_id: int
    invoice_number: str
    refund_amount: Decimal
    balance_amount: Decimal
    status: str
    customer_name: str
    customer_phone: str
    store_name: str
    valid_until: Optional[str] = None
    created_at: datetime
    thermal_text: str
    html: Optional[str] = None

    model_config = {"from_attributes": True}



class PaymentSplit(BaseModel):
    payment_mode: str = Field(description="Must be a valid payment mode")
    amount: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Amount must be greater than 0",
    )
    transaction_reference: Optional[str] = Field(
        default=None,
        max_length=255,
    )
    amount_tendered: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("999999.99"),
        description="Cash tendered amount by customer (applicable for cash payments)",
    )
    change_due: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Change due returned to customer",
    )

    @field_validator("payment_mode")
    @classmethod
    def validate_payment_mode(cls, v: str) -> str:
        if v not in VALID_PAYMENT_MODES:
            raise ValueError(
                f"payment_mode must be one of {VALID_PAYMENT_MODES}"
            )
        return v

    @field_validator("transaction_reference", mode="before")
    @classmethod
    def validate_transaction_reference(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("transaction_reference must be a string")
        value = value.strip()
        if not value or value.lower() in {"string", "null", "none", "undefined"}:
            raise ValueError("transaction_reference cannot be empty or a placeholder")
        return value


class TenderPaymentSplit(BaseModel):
    mode: str = Field(description="Payment mode like upi, card, wallet")
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class TenderChangeRequest(BaseModel):
    payable_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="Total amount payable")
    tendered_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2, description="Cash tendered by customer")
    other_payments: Optional[list[TenderPaymentSplit]] = Field(default=None, description="Other non-cash payments like UPI/Card")
    calculate_denominations: Optional[bool] = Field(default=False, description="Whether to calculate currency denomination breakdown")


class TenderChangeResponse(BaseModel):
    payable_amount: Decimal
    tendered_amount: Decimal
    other_payments_total: Decimal = Decimal("0.00")
    net_payable_cash: Decimal = Decimal("0.00")
    change_due: Decimal
    is_exact: bool
    denominations: Optional[dict[str, int]] = None
    status: str = "success"


class InvoiceItemCreate(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, description="Quantity must be positive")
    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Unit price; fetched from product if omitted",
    )
    discount: Decimal = Field(
        default=Decimal("0.0"),
        ge=0,
        description="Line item discount",
    )


class InvoiceCreate(BaseModel):
    store_id: int = Field(gt=0, description="Store ID must be positive")
    customer_id: Optional[int] = Field(default=None, gt=0)
    same_state: bool = True
    items: Optional[list[InvoiceItemCreate]] = Field(
        default=None,
        description=(
            "Optional direct line items. If omitted, items from user's "
            "active cart will be used."
        ),
    )
    payments: list["PaymentSplit"] = Field(
        default_factory=list,
        max_length=5,
    )
    shift_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional active POS Shift ID to link invoice and payments",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional idempotency key to prevent duplicate checkouts",
    )


class ReturnItemRequest(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    product_id: int = Field(gt=0, description="Product ID must be positive")
    return_quantity: Decimal = Field(
        gt=0,
        le=Decimal("10000"),
        description="Return quantity must be greater than 0",
    )
    reason: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        validation_alias=AliasChoices("reason", "notes"),
    )
    condition: str = Field(
        default="sellable",
        description="Item condition: sellable, damaged, expired",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Optional idempotency key",
    )
    issue_credit_note: bool = Field(
        default=False,
        description="Whether to atomically issue credit note",
    )
    refund_method: str = Field(
        default="cash",
        description="Refund method if issuing credit note",
    )

    @field_validator("condition", mode="before")
    @classmethod
    def validate_condition(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("condition must be one of: sellable, damaged, expired")
        value = value.strip().lower()
        if value not in {"sellable", "damaged", "expired"}:
            raise ValueError("condition must be one of: sellable, damaged, expired")
        return value

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def validate_idempotency_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("idempotency_key must be a string")
        value = value.strip()
        if (
            not value
            or value.lower() in {"string", "null", "none", "undefined"}
            or any(character.isspace() for character in value)
        ):
            raise ValueError("idempotency_key must be a non-empty token without spaces")
        return value

    @field_validator("refund_method", mode="before")
    @classmethod
    def validate_return_refund_method(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"refund_method must be one of {VALID_REFUND_METHODS}"
            )
        value = value.strip().lower()
        if value not in VALID_REFUND_METHODS:
            raise ValueError(
                f"refund_method must be one of {VALID_REFUND_METHODS}"
            )
        return value


class ThermalPrintResponse(BaseModel):
    printer_type: str
    encoding: str
    payload: str
    byte_payload: str
