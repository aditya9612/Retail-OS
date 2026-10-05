from datetime import datetime
import math
import re
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)


VALID_PAYMENT_METHODS = {
    "cash",
    "card",
    "credit_card",
    "debit_card",
    "upi",
    "wallet",
    "qr",
    "bank_transfer",
    "cheque",
    "other",
    "credit",
}

VALID_PAYMENT_STATUSES = {
    "paid",
    "pending",
    "partially_paid",
    "failed",
    "cancelled",
    "refunded",
    "completed",
}


# ============================================================
# SALE ITEM CREATE
# ============================================================

class SaleItemCreate(BaseModel):
    product_id: StrictInt = Field(
        ...,
        gt=0,
        description="Product ID must be a positive integer",
    )

    quantity: StrictInt = Field(
        ...,
        gt=0,
        le=100000,
        description="Quantity must be greater than 0 and at most 100,000",
    )

    stock: Optional[StrictInt] = Field(
        default=None,
        ge=0,
        le=100000,
        description="Stock quantity must be non-negative and at most 100,000",
    )

    unit_price: Optional[float] = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Unit price must be greater than or equal to 0",
    )

    tax_rate: Optional[float] = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Tax rate must be greater than or equal to 0",
    )

    tax_amount: Optional[float] = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Tax amount must be greater than or equal to 0",
    )

    discount: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="Discount must be greater than or equal to 0",
    )

    @field_validator("product_id", mode="before")
    @classmethod
    def validate_product_id(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Product ID must be a valid integer.")

        if value <= 0:
            raise ValueError("Product ID must be greater than 0.")

        return value

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Quantity must be a valid integer.")

        if value <= 0:
            raise ValueError("Quantity must be greater than 0.")

        if value > 100000:
            raise ValueError("Quantity must not exceed 100,000.")

        return value

    @field_validator("stock", mode="before")
    @classmethod
    def validate_stock(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Stock must be a valid integer.")

        if value < 0:
            raise ValueError("Stock must be greater than or equal to 0.")

        if value > 100000:
            raise ValueError("Stock must not exceed 100,000.")

        return value

    @field_validator(
        "unit_price",
        "tax_rate",
        "tax_amount",
        "discount",
        mode="before",
    )
    @classmethod
    def validate_numeric_values(cls, value, info):
        if value is None:
            return value

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"{info.field_name.replace('_', ' ').title()} "
                "must be a valid number."
            )

        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                f"{info.field_name.replace('_', ' ').title()} "
                "must be a finite number."
            )

        if value < 0:
            raise ValueError(
                f"{info.field_name.replace('_', ' ').title()} "
                "must be greater than or equal to 0."
            )

        return value


# ============================================================
# SALE CREATE
# ============================================================

class SaleCreate(BaseModel):
    store_id: StrictInt = Field(
        ...,
        gt=0,
        description="Store ID must be a positive integer",
    )

    sale_number: StrictStr = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Sale reference number",
    )

    invoice_number: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Invoice reference number",
    )

    customer_id: Optional[StrictInt] = Field(
        default=None,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    payment_method: StrictStr = Field(
        default="cash",
        description="Payment method",
    )

    payment_status: StrictStr = Field(
        default="paid",
        description="Payment status",
    )

    items: List[SaleItemCreate] = Field(
        ...,
        min_length=1,
        description="Sale must contain at least one item",
    )

    @field_validator("store_id", mode="before")
    @classmethod
    def validate_store_id(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Store ID must be a valid integer.")

        if value <= 0:
            raise ValueError("Store ID must be greater than 0.")

        return value

    @field_validator("customer_id", mode="before")
    @classmethod
    def validate_customer_id(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Customer ID must be a valid integer.")

        if value <= 0:
            raise ValueError("Customer ID must be greater than 0.")

        return value

    @field_validator("sale_number", mode="before")
    @classmethod
    def validate_sale_number(cls, value):
        if not isinstance(value, str):
            raise ValueError("Sale number must be a valid string.")

        value = value.strip()

        if not value:
            raise ValueError(
                "Sale number cannot be empty or whitespace only."
            )

        return value

    @field_validator("invoice_number", mode="before")
    @classmethod
    def validate_invoice_number(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError("Invoice number must be a valid string.")

        value = value.strip()

        if not value:
            raise ValueError(
                "Invoice number cannot be empty or whitespace only."
            )

        return value


    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, value):
        if not isinstance(value, str):
            raise ValueError("Payment method must be a valid string.")

        cleaned = value.strip().lower()
        normalized = re.sub(r"[\s-]+", "_", cleaned)

        if not normalized or normalized not in VALID_PAYMENT_METHODS:
            raise ValueError(
                "Invalid payment method. Allowed values: "
                + ", ".join(sorted(VALID_PAYMENT_METHODS))
            )

        return normalized

    @field_validator("payment_status", mode="before")
    @classmethod
    def validate_payment_status(cls, value):
        if not isinstance(value, str):
            raise ValueError("Payment status must be a valid string.")

        cleaned = value.strip().lower()
        normalized = re.sub(r"[\s-]+", "_", cleaned)

        if not normalized or normalized not in VALID_PAYMENT_STATUSES:
            raise ValueError(
                "Invalid payment status. Allowed values: "
                + ", ".join(sorted(VALID_PAYMENT_STATUSES))
            )

        return normalized

    @field_validator("items")
    @classmethod
    def validate_items(
        cls,
        items: List[SaleItemCreate],
    ) -> List[SaleItemCreate]:

        if not items:
            raise ValueError("Sale must contain at least one item.")

        seen_products = set()

        for item in items:
            if item.product_id in seen_products:
                raise ValueError(
                    f"Duplicate product ID {item.product_id} found "
                    "in sale items. Each product can only appear once "
                    "per sale."
                )

            seen_products.add(item.product_id)

        return items


# ============================================================
# SALE ITEM UPDATE
# ============================================================

class SaleItemUpdate(BaseModel):
    product_id: Optional[StrictInt] = Field(
        default=None,
        gt=0,
        description="Product ID must be a positive integer",
    )

    quantity: Optional[StrictInt] = Field(
        default=None,
        gt=0,
        le=100000,
        description="Quantity must be greater than 0 and at most 100,000",
    )

    stock: Optional[StrictInt] = Field(
        default=None,
        ge=0,
        le=100000,
        description="Stock quantity must be non-negative and at most 100,000",
    )

    unit_price: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Unit price must be greater than or equal to 0",
    )

    tax_rate: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Tax rate must be greater than or equal to 0",
    )

    tax_amount: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Tax amount must be greater than or equal to 0",
    )

    discount: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Discount must be greater than or equal to 0",
    )

    @field_validator("product_id", mode="before")
    @classmethod
    def validate_product_id(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Product ID must be a valid integer.")

        if value <= 0:
            raise ValueError("Product ID must be greater than 0.")

        return value

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Quantity must be a valid integer.")

        if value <= 0:
            raise ValueError("Quantity must be greater than 0.")

        if value > 100000:
            raise ValueError("Quantity must not exceed 100,000.")

        return value

    @field_validator("stock", mode="before")
    @classmethod
    def validate_stock(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Stock must be a valid integer.")

        if value < 0:
            raise ValueError("Stock must be greater than or equal to 0.")

        if value > 100000:
            raise ValueError("Stock must not exceed 100,000.")

        return value

    @field_validator(
        "unit_price",
        "tax_rate",
        "tax_amount",
        "discount",
        mode="before",
    )
    @classmethod
    def validate_numeric_values(cls, value, info):
        if value is None:
            return value

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"{info.field_name.replace('_', ' ').title()} "
                "must be a valid number."
            )

        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                f"{info.field_name.replace('_', ' ').title()} "
                "must be a finite number."
            )

        if value < 0:
            raise ValueError(
                f"{info.field_name.replace('_', ' ').title()} "
                "must be greater than or equal to 0."
            )

        return value


# ============================================================
# SALE UPDATE
# ============================================================

class SaleUpdate(BaseModel):
    store_id: Optional[StrictInt] = Field(
        default=None,
        gt=0,
        description="Store ID must be a positive integer",
    )

    sale_number: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Sale reference number",
    )

    invoice_number: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Invoice reference number",
    )

    customer_id: Optional[StrictInt] = Field(
        default=None,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    payment_method: Optional[StrictStr] = Field(
        default=None,
        description="Payment method",
    )

    payment_status: Optional[StrictStr] = Field(
        default=None,
        description="Payment status",
    )

    items: Optional[List[SaleItemUpdate]] = Field(
        default=None,
        min_length=1,
        description="Updated sale items",
    )

    @field_validator("store_id", mode="before")
    @classmethod
    def validate_store_id(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Store ID must be a valid integer.")

        if value <= 0:
            raise ValueError("Store ID must be greater than 0.")

        return value

    @field_validator("customer_id", mode="before")
    @classmethod
    def validate_customer_id(cls, value):
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Customer ID must be a valid integer.")

        if value <= 0:
            raise ValueError("Customer ID must be greater than 0.")

        return value

    @field_validator("sale_number", mode="before")
    @classmethod
    def validate_sale_number(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Sale number must be a valid string.")
        value = value.strip()
        if not value:
            raise ValueError("Sale number cannot be empty or whitespace only.")
        return value

    @field_validator("invoice_number", mode="before")
    @classmethod
    def validate_invoice_number(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError("Invoice number must be a valid string.")

        value = value.strip()

        if not value:
            raise ValueError(
                "Invoice number cannot be empty or whitespace only."
            )

        return value


    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError("Payment method must be a valid string.")

        cleaned = value.strip().lower()
        normalized = re.sub(r"[\s-]+", "_", cleaned)

        if not normalized or normalized not in VALID_PAYMENT_METHODS:
            raise ValueError(
                "Invalid payment method. Allowed values: "
                + ", ".join(sorted(VALID_PAYMENT_METHODS))
            )

        return normalized

    @field_validator("payment_status", mode="before")
    @classmethod
    def validate_payment_status(cls, value):
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError("Payment status must be a valid string.")

        cleaned = value.strip().lower()
        normalized = re.sub(r"[\s-]+", "_", cleaned)

        if not normalized or normalized not in VALID_PAYMENT_STATUSES:
            raise ValueError(
                "Invalid payment status. Allowed values: "
                + ", ".join(sorted(VALID_PAYMENT_STATUSES))
            )

        return normalized

    @field_validator("items")
    @classmethod
    def validate_items(cls, items):
        if items is None:
            return None

        if not items:
            raise ValueError("Sale must contain at least one item.")

        seen_products = set()

        for item in items:
            if item.product_id is not None:
                if item.product_id in seen_products:
                    raise ValueError(
                        f"Duplicate product ID {item.product_id} found "
                        "in sale items. Each product can only appear once "
                        "per sale."
                    )

                seen_products.add(item.product_id)

        return items


# ============================================================
# SALE ITEM RESPONSE
# ============================================================

class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    total_price: float
    discount: float = 0.0
    tax: float = 0.0

    model_config = ConfigDict(
        from_attributes=True
    )


# ============================================================
# SALE RESPONSE
# ============================================================

class SaleResponse(BaseModel):
    id: int
    store_id: int
    tenant_id: Optional[int] = None
    sale_number: Optional[str] = None
    invoice_number: str
    subtotal: float
    tax_amount: Optional[float] = 0.0
    total_amount: float
    payment_method: str
    payment_status: Optional[str] = "paid"
    status: str
    discount: float = 0.0
    tax: float = 0.0
    customer_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[SaleItemResponse] = []

    model_config = ConfigDict(
        from_attributes=True
    )

