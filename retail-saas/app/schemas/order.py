from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict,  Field, StrictInt, field_validator, model_validator

VALID_ORDER_TYPES = ["pos", "ecommerce"]
VALID_ORDER_STATUSES = [
    "draft", "confirmed", "processing",
    "shipped", "delivered", "cancelled",
    "returned", "refunded"
]
VALID_PAYMENT_METHODS = ["cash", "upi", "card", "credit_card", "debit_card", "wallet", "qr"]

INVALID_STRING_VALUES = ["string", "null", "none", "undefined", "test", "null value", "n/a", "na"]


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

    @field_validator("variant")
    @classmethod
    def validate_variant(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError("Variant cannot be empty")

        if v.lower() in INVALID_STRING_VALUES:
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

        if v.isdigit():
            raise ValueError("Variant cannot contain only numbers")

        return v

class OrderItemResponse(BaseModel):

    id: int
    product_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    variant: Optional[str]

    model_config = {
        "from_attributes": True
    }

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
        ...,
        min_length=3,
        max_length=500,
        description="Delivery address is required",
    )

    notes: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000,
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
        v: str,
    ) -> str:

        if v is None:
            raise ValueError("Delivery address is required")

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

        product_ids = [
            item.product_id
            for item in v
        ]

        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Order cannot contain duplicate products")

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

    delivery_address: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
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
    customer_id: Optional[int]
    order_number: str
    order_type: str
    status: str
    coupon_code: Optional[str]
    discount_amount: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    delivery_address: Optional[str]
    delivery_status: Optional[str]
    notes: Optional[str]
    items: List[OrderItemResponse] =  Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    invoice_number: str
    status: str
    subtotal: Decimal
    discount_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    pdf_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentCreate(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    order_id: StrictInt = Field(
        ...,
        gt=0,
        description="Order ID must be positive",
    )

    payment_method: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )

    amount: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("999999.99"),
        description="Payment amount must be greater than 0",
    )

    transaction_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(
        cls,
        v: str,
    ) -> str:

        v = v.strip().lower()

        if not v:
            raise ValueError(
                "Payment method cannot be empty"
            )

        if v in INVALID_STRING_VALUES:
            raise ValueError(
                "Invalid payment method"
            )

        if v not in VALID_PAYMENT_METHODS:
            raise ValueError(
                f"payment_method must be one of {VALID_PAYMENT_METHODS}"
            )

        return v

    @field_validator("amount", mode="before")
    @classmethod
    def validate_payment_amount(cls, v):

        if isinstance(v, str):

            value = v.strip().lower()

            if value in INVALID_STRING_VALUES:
                raise ValueError(
                    "Invalid payment amount"
                )

            if value == "":
                raise ValueError(
                    "Payment amount cannot be empty"
                )

        return v
    
    @field_validator("transaction_id")
    @classmethod
    def validate_transaction_id(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if v is None:
            return None

        v = v.strip()

        if not v:
            raise ValueError(
                "Transaction ID cannot be empty"
            )

        if v.lower() in INVALID_STRING_VALUES:
            raise ValueError(
                "Invalid transaction ID"
            )

        return v

    
class PaymentResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    payment_method: str
    status: str
    amount: Decimal
    transaction_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
    

class OrderTrackingResponse(BaseModel):
    id: int
    order_id: int
    status: str
    remarks: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}
    
    
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
