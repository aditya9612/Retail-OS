
from datetime import datetime
from decimal import Decimal
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


class InvoiceReprintRequest(BaseModel):
    printer_type: str = Field(default="generic", min_length=1, max_length=50)

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


class RefundCreate(BaseModel):
    invoice_id: int = Field(gt=0, description="Invoice ID must be positive")
    refund_amount: Decimal = Field(
        gt=0,
        le=Decimal("999999.99"),
        description="Refund amount must be greater than 0",
    )
    refund_method: str = Field(description="Must be cash, upi or store_credit")
    reason: Optional[str] = Field(default=None, min_length=3, max_length=500)

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
        if isinstance(v, str):
            v = v.strip()
            if len(v) < 3:
                raise ValueError(
                    "Reason must contain at least 3 non-whitespace characters"
                )
            if len(v) > 500:
                raise ValueError("Reason cannot exceed 500 characters")
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


class TenderChangeRequest(BaseModel):
    payable_amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Total amount payable",
    )
    tendered_amount: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Cash tendered by customer",
    )


class TenderChangeResponse(BaseModel):
    payable_amount: Decimal
    tendered_amount: Decimal
    change_due: Decimal
    is_exact: bool
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
