
import re
from enum import Enum
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)
from app.utils.validators import validate_single_pincode


VALID_ORDER_TYPES = ["pos", "ecommerce", "online"]

VALID_ORDER_STATUSES = [
    "draft",
    "pending",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "returned",
    "partially_returned",
    "refunded",
]

VALID_PAYMENT_METHODS = [
    "cash",
    "upi",
    "card",
    "credit_card",
    "debit_card",
    "wallet",
    "qr",
    "credit",
    "khata",
    "customer_credit",
    "cod",
    "net_banking",
    "bank_transfer",
    "cheque",
]

VALID_DELIVERY_STATUSES = [
    "pending",
    "assigned",
    "in_transit",
    "picked_up",
    "out_for_delivery",
    "delivered",
    "cancelled",
    "failed",
    "returned",
]

INVALID_STRING_VALUES = [
    "string",
    "null",
    "none",
    "undefined",
    "test",
    "null value",
    "n/a",
    "na",
    "nausomd",
    "dummy",
    "sample",
    "placeholder",
]

FORBIDDEN_VARIANT_SYMBOLS = set(r"\|[]{}<>~`^")


class OrderItemCreate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    product_id: int = Field(
        ...,
        gt=0,
        description="Product ID must be a positive integer",
    )

    quantity: int = Field(
        ...,
        gt=0,
        le=10000,
        description="Quantity must be between 1 and 10000",
    )

    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        description="Unit price must be greater than 0",
    )

    discount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("999999.99"),
        description="Item discount cannot be negative",
    )

    variant: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Variant cannot be empty",
    )

    variant_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional Product Variant ID",
    )

    @field_validator("unit_price", "discount", mode="before")
    @classmethod
    def validate_decimal_values(cls, v):

        if v is None:
            return v

        if isinstance(v, str):
            value = v.strip().lower()

            if value in INVALID_STRING_VALUES:
                raise ValueError("Invalid numeric value")

            if value == "":
                raise ValueError("Numeric value cannot be empty")

        return v

    @field_validator("variant", mode="before")
    @classmethod
    def validate_variant(
        cls,
        v: Any,
    ) -> Optional[str]:

        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Variant must be a valid string")

        v = v.strip()

        if not v:
            raise ValueError("Variant cannot be empty or whitespace")

        clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
        if v.lower() in INVALID_STRING_VALUES or clean_norm in INVALID_STRING_VALUES:
            raise ValueError("Invalid variant value")

        invalid_variants = {
            "0",
            "0kg",
            "0 kg",
            "0ml",
            "0 ml",
            "0pcs",
            "0 pcs",
            "0piece",
            "0 piece",
            "0unit",
            "0 unit",
        }

        if v.lower() in invalid_variants:
            raise ValueError("Invalid variant value")

        if v.isdigit() or (clean_norm.isdigit() and not any(c.isalpha() for c in v)):
            raise ValueError("Variant cannot contain only numbers")

        if any(c in FORBIDDEN_VARIANT_SYMBOLS for c in v):
            raise ValueError("Variant contains invalid characters")

        if not any(c.isalnum() for c in v):
            raise ValueError("Variant must contain alphanumeric characters")

        if re.search(r"[-+@#*/=_.,:;?!&$%]{2,}", v):
            raise ValueError("Variant cannot contain consecutive symbols")

        if re.search(r"(.)\1{3,}", v, re.IGNORECASE):
            raise ValueError(f"Variant cannot contain repetitive characters in '{v}'")

        if re.search(r"[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{5,}", v):
            raise ValueError(f"Variant contains invalid character sequence in '{v}'")

        return v


class OrderItemBatchAllocationResponse(BaseModel):
    id: int
    order_item_id: int
    batch_id: int
    quantity: Decimal
    unit_cost: Decimal
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class OrderItemResponse(BaseModel):

    id: int
    product_id: int
    product_name: str = ""
    sku: str = ""
    quantity: int
    unit_price: Decimal = Decimal("0.00")
    discount: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    notes: Optional[str] = None
    variant: Optional[str] = None
    variant_id: Optional[int] = None
    batch_allocations: Optional[List[OrderItemBatchAllocationResponse]] = None

    model_config = {
        "from_attributes": True
    }

    @field_validator(
        "unit_price",
        "discount",
        "discount_amount",
        "tax_rate",
        "tax_amount",
        "total",
        "total_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        mode="before",
    )
    @classmethod
    def coerce_item_decimals(cls, v):
        if v is None:
            return Decimal("0.00")
        return v


class OrderCreate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    store_id: int = Field(
        ...,
        gt=0,
        description="Store ID must be a positive integer",
    )

    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    order_type: str = Field(
        default="pos",
        min_length=1,
        max_length=20,
        description="Order type must be pos or ecommerce",
    )

    payment_method: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
        description="Payment method: cash, upi, card, cod, wallet, net_banking, credit, etc.",
    )

    coupon_code: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=50,
    )

    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("100"),
        description="Discount percentage must be between 0 and 100",
    )

    delivery_address: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Delivery address is optional for POS orders",
    )

    delivery_pincode: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=6,
        pattern=r"^[1-9][0-9]{5}$",
        description="Optional delivery pincode (6-digit Indian PIN)",
    )

    delivery_status: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
        description="Delivery status: pending, assigned, in_transit, out_for_delivery, delivered, cancelled",
    )

    notes: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )

    same_state: bool = Field(
        default=True,
        description="True for intra-state (CGST+SGST), False for inter-state (IGST)",
    )

    items: List[OrderItemCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Order must contain 1 to 100 items",
    )

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:

        v = v.strip().lower()

        if not v:
            raise ValueError("Order type cannot be empty")

        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid order type")

        if v not in VALID_ORDER_TYPES:
            raise ValueError(f"order_type must be one of {VALID_ORDER_TYPES}")

        return v

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(
        cls,
        v: Any,
    ) -> Optional[str]:

        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Payment method must be a valid string")

        v = v.strip().lower()

        if not v:
            raise ValueError("Payment method cannot be empty")

        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid payment method")

        if v not in VALID_PAYMENT_METHODS:
            raise ValueError(
                f"payment_method must be one of {VALID_PAYMENT_METHODS}"
            )

        return v

    @field_validator("delivery_status", mode="before")
    @classmethod
    def validate_delivery_status(
        cls,
        v: Any,
    ) -> Optional[str]:

        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Delivery status must be a valid string")

        v = v.strip().lower()

        if not v:
            raise ValueError("Delivery status cannot be empty")

        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid delivery status")

        if v not in VALID_DELIVERY_STATUSES:
            raise ValueError(
                f"delivery_status must be one of {VALID_DELIVERY_STATUSES}"
            )

        return v

    @field_validator("coupon_code")
    @classmethod
    def validate_coupon_code(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Coupon code cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid coupon code")

        return v.upper()

    @field_validator("discount_amount", mode="before")
    @classmethod
    def validate_discount_amount(cls, v):

        if isinstance(v, str):

            value = v.strip().lower()

            if value in INVALID_STRING_VALUES:
                raise ValueError("Invalid discount value")

            if value == "":
                raise ValueError("Discount percentage cannot be empty")

        return v

    @field_validator("delivery_address")
    @classmethod
    def validate_delivery_address(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Delivery address cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid delivery address")

        if len(v) < 3:
            raise ValueError("Delivery address is too short")

        if v.isdigit():
            raise ValueError("Delivery address cannot contain only numbers")

        return v

    @field_validator("delivery_pincode")
    @classmethod
    def validate_delivery_pincode(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            return None

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid delivery pincode")

        return validate_single_pincode(v)

    @field_validator("notes")
    @classmethod
    def validate_notes(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Notes cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid notes")

        return v

    @field_validator("items")
    @classmethod
    def validate_items(
        cls,
        v: List[OrderItemCreate],
    ) -> List[OrderItemCreate]:

        if not v:
            raise ValueError("Order must contain at least one item")

        item_keys = [
            (item.product_id, getattr(item, "variant_id", None))
            for item in v
        ]

        if len(item_keys) != len(set(item_keys)):
            raise ValueError("Order cannot contain duplicate products or variants")

        return v


class OrderUpdate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Customer ID must be positive",
    )

    coupon_code: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=50,
    )

    discount_amount: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=Decimal("100"),
        description="Discount percentage must be between 0 and 100",
    )

    payment_method: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
        description="Optional payment method update: cash, upi, card, cod, wallet, etc.",
    )

    delivery_address: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
    )

    delivery_pincode: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=6,
        pattern=r"^[1-9][0-9]{5}$",
        description="Optional delivery pincode (6-digit Indian PIN)",
    )

    delivery_status: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
        description="Optional delivery status update: pending, assigned, in_transit, out_for_delivery, delivered, cancelled",
    )

    notes: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )

    status: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=30,
    )

    items: Optional[List[OrderItemCreate]] = Field(
        default=None,
        description="Optional replacement items for draft order",
    )

    @field_validator("coupon_code")
    @classmethod
    def validate_coupon_code(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Coupon code cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid coupon code")

        return v.upper()

    @field_validator("discount_amount", mode="before")
    @classmethod
    def validate_discount_amount(cls, v):

        if v is None:
            return None

        if isinstance(v, str):

            value = v.strip().lower()

            if value in INVALID_STRING_VALUES:
                raise ValueError("Invalid discount value")

            if value == "":
                raise ValueError("Discount percentage cannot be empty")

        return v

    @field_validator("delivery_address")
    @classmethod
    def validate_delivery_address(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Delivery address cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid delivery address")

        if len(v) < 3:
            raise ValueError("Delivery address is too short")

        if v.isdigit():
            raise ValueError("Delivery address cannot contain only numbers")

        return v

    @field_validator("delivery_pincode")
    @classmethod
    def validate_delivery_pincode(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            return None

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid delivery pincode")

        return validate_single_pincode(v)

    @field_validator("notes")
    @classmethod
    def validate_notes(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Notes cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid notes")

        return v

    @field_validator("status")
    @classmethod
    def validate_status(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip().lower()

        if not v:
            raise ValueError("Status cannot be empty")

        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid status")

        if v not in VALID_ORDER_STATUSES:
            raise ValueError(f"status must be one of {VALID_ORDER_STATUSES}")

        return v

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(
        cls,
        v: Any,
    ) -> Optional[str]:

        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Payment method must be a valid string")

        v = v.strip().lower()

        if not v:
            raise ValueError("Payment method cannot be empty")

        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid payment method")

        if v not in VALID_PAYMENT_METHODS:
            raise ValueError(
                f"payment_method must be one of {VALID_PAYMENT_METHODS}"
            )

        return v

    @field_validator("delivery_status", mode="before")
    @classmethod
    def validate_delivery_status(
        cls,
        v: Any,
    ) -> Optional[str]:

        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Delivery status must be a valid string")

        v = v.strip().lower()

        if not v:
            raise ValueError("Delivery status cannot be empty")

        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid delivery status")

        if v not in VALID_DELIVERY_STATUSES:
            raise ValueError(
                f"delivery_status must be one of {VALID_DELIVERY_STATUSES}"
            )

        return v

    @model_validator(mode="after")
    def validate_update_fields(self):

        if not self.model_fields_set:
            raise ValueError(
                "At least one field is required for update"
            )

        return self


class OrderResponse(BaseModel):

    id: int
    tenant_id: int
    store_id: int
    customer_id: Optional[int] = None
    order_number: str
    order_type: str
    status: str
    coupon_code: Optional[str] = None
    discount_amount: Decimal = Decimal("0.00")
    subtotal: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    round_off: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    payment_status: Optional[str] = "pending"
    payment_method: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_pincode: Optional[str] = None
    delivery_status: Optional[str] = None
    notes: Optional[str] = None
    items: List[OrderItemResponse] = Field(default_factory=list)
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

    @field_validator(
        "discount_amount",
        "subtotal",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "tax_amount",
        "round_off",
        "total_amount",
        mode="before",
    )
    @classmethod
    def coerce_order_decimals(cls, v):
        if v is None:
            return Decimal("0.00")
        return v


class InvoiceItemResponse(BaseModel):
    id: int
    product_id: int
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    product_name: str = ""
    sku: str = ""
    barcode: Optional[str] = None
    hsn_code: Optional[str] = None
    unit: str = "pcs"
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    gst_rate: Decimal
    gst_amount: Decimal
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    total_amount: Decimal
    returned_quantity: Decimal = Decimal("0.0000")

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def enrich_from_product(cls, value):
        if isinstance(value, dict):
            return value
        product = getattr(value, "product", None)
        variant_rel = getattr(value, "variant_rel", None)
        if product is None and variant_rel is None:
            return value

        data = {
            "id": value.id,
            "product_id": value.product_id,
            "variant_id": getattr(value, "variant_id", None),
            "variant_name": getattr(value, "variant_name", None) or (getattr(variant_rel, "variant_name", None) if variant_rel else None),
            "product_name": getattr(value, "product_name", None) or (getattr(product, "name", "") if product else ""),
            "sku": getattr(value, "sku", None) or (getattr(variant_rel, "sku", None) if variant_rel else None) or (getattr(product, "sku", "") if product else ""),
            "barcode": getattr(value, "barcode", None) or (getattr(variant_rel, "barcode", None) if variant_rel else None) or (getattr(product, "barcode", None) if product else None),
            "hsn_code": getattr(value, "hsn_code", None) or (getattr(product, "hsn_code", None) if product else None),
            "unit": getattr(value, "unit", None) or (getattr(product, "unit", None) if product else None) or "pcs",
            "quantity": value.quantity,
            "unit_price": value.unit_price,
            "discount_amount": value.discount_amount or Decimal("0.00"),
            "gst_rate": value.gst_rate,
            "gst_amount": value.gst_amount,
            "cgst_amount": getattr(value, "cgst_amount", None) or Decimal("0.00"),
            "sgst_amount": getattr(value, "sgst_amount", None) or Decimal("0.00"),
            "igst_amount": getattr(value, "igst_amount", None) or Decimal("0.00"),
            "total_amount": value.total_amount,
            "returned_quantity": getattr(value, "returned_quantity", None) or Decimal("0.0000"),
        }
        return data


class PaymentResponse(BaseModel):

    id: int
    tenant_id: int
    order_id: int
    payment_method: str
    payment_mode: str = Field(
        validation_alias=AliasChoices("payment_mode", "payment_method")
    )
    status: str
    amount: Decimal
    transaction_id: Optional[str]
    transaction_reference: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("transaction_reference", "transaction_id"),
    )
    amount_tendered: Optional[Decimal] = None
    change_due: Optional[Decimal] = None
    created_at: datetime
    qr_payload: Optional[str] = None
    qr_code_base64: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_payment_amount(cls, v):
        if v is None:
            return Decimal("0.00")
        return v


class InvoiceResponse(BaseModel):

    id: int
    tenant_id: int
    store_id: Optional[int] = None
    order_id: int
    customer_id: Optional[int] = None
    same_state: Optional[bool] = None
    invoice_number: str
    status: str
    subtotal: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    pdf_url: Optional[str] = None
    items: List[InvoiceItemResponse] = Field(default_factory=list)
    payments: List[PaymentResponse] = Field(default_factory=list)
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

    @field_validator(
        "subtotal",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "total_amount",
        mode="before",
    )
    @classmethod
    def coerce_invoice_decimals(cls, v):
        if v is None:
            return Decimal("0.00")
        return v



class OrderTrackingResponse(BaseModel):

    id: int
    order_id: int
    status: str
    remarks: Optional[str]
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


class OrderStatusUpdateRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    remarks: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    @field_validator("status")
    @classmethod
    def validate_status(
        cls,
        v: str,
    ) -> str:

        v = v.strip().lower()

        if not v:
            raise ValueError(
                "Status cannot be empty"
            )

        if v in INVALID_STRING_VALUES:
            raise ValueError(
                "Invalid status"
            )

        if v not in VALID_ORDER_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_ORDER_STATUSES}"
            )

        return v

    @field_validator("remarks")
    @classmethod
    def validate_remarks(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError(
                "Remarks cannot be empty"
            )

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError(
                "Invalid remarks"
            )

        return v


class OrderAddItemsRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    items: List[OrderItemCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Items to add to the draft order",
    )


class POSPaymentData(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    payment_method: str = Field(
        default="cash",
        description="Payment method: cash, upi, card, credit_card, debit_card, wallet",
    )

    amount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Amount tendered by customer. If None, exactly order total is used.",
    )

    transaction_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional external transaction reference or UTR",
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    @field_validator("payment_method")
    @classmethod
    def validate_pos_payment_method(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Payment method cannot be empty")
        if v in INVALID_STRING_VALUES:
            raise ValueError("Invalid payment method")
        return v


class POSCheckoutRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    store_id: int = Field(
        ...,
        gt=0,
        description="Store ID where POS transaction is occurring",
    )

    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional customer ID for loyalty and purchase history",
    )

    coupon_code: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=50,
    )

    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=Decimal("100"),
        description="Overall discount percentage (0 to 100)",
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    same_state: bool = Field(
        default=True,
        description="True for intra-state (CGST+SGST), False for inter-state (IGST)",
    )

    items: List[OrderItemCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    payment: POSPaymentData = Field(
        default_factory=POSPaymentData,
        description="Payment details for instant settlement",
    )

    generate_invoice: bool = Field(
        default=True,
        description="Whether to generate an official tax invoice immediately",
    )

    @field_validator("coupon_code")
    @classmethod
    def validate_pos_coupon_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Coupon code cannot be empty")
        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError("Invalid coupon code")
        return v.upper()

    @field_validator("items")
    @classmethod
    def validate_pos_items(cls, v: List[OrderItemCreate]) -> List[OrderItemCreate]:
        if not v:
            raise ValueError("Order must contain at least one item")
        item_keys = [
            (item.product_id, getattr(item, "variant_id", None))
            for item in v
        ]
        if len(item_keys) != len(set(item_keys)):
            raise ValueError("Order cannot contain duplicate products or variants")
        return v


class POSCheckoutResponse(BaseModel):
    order: OrderResponse
    payment: Optional[PaymentResponse] = None
    invoice: Optional[InvoiceResponse] = None
    change_due: Decimal = Decimal("0.00")

    model_config = {
        "from_attributes": True
    }


class OrderCounts(BaseModel):
    """Order status summary counts for list view display."""

    total: int = 0
    draft: int = 0
    pending: int = 0
    confirmed: int = 0
    processing: int = 0
    packed: int = 0
    dispatched: int = 0
    out_for_delivery: int = 0
    delivered: int = 0
    completed: int = 0
    cancelled: int = 0


class OrderStatsResponse(BaseModel):
    total_orders: int
    total_revenue: Decimal
    draft_orders: int
    confirmed_orders: int
    completed_orders: int
    cancelled_orders: int
    average_order_value: Decimal

    model_config = {
        "from_attributes": True
    }


class OrderReceiptItemResponse(BaseModel):
    name: str
    quantity: int
    unit_price: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")

    @field_validator(
        "unit_price",
        "tax_amount",
        "discount_amount",
        "total_amount",
        mode="before",
    )
    @classmethod
    def coerce_receipt_item_decimals(cls, v):
        if v is None:
            return Decimal("0.00")
        return v


class OrderThermalMode(str, Enum):
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


class OrderReceiptResponse(BaseModel):
    order_id: int
    order_number: str
    store_name: str
    store_code: Optional[str] = None
    store_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: List[OrderReceiptItemResponse]
    subtotal: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    round_off: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    payment_status: str
    payment_method: Optional[str] = None
    created_at: datetime
    formatted_receipt: str

    model_config = {
        "from_attributes": True
    }

    @field_validator(
        "subtotal",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "tax_amount",
        "round_off",
        "total_amount",
        mode="before",
    )
    @classmethod
    def coerce_receipt_decimals(cls, v):
        if v is None:
            return Decimal("0.00")
        return v
