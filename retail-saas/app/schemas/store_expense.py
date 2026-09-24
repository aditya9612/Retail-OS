from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)


class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    OTHER = "other"


# ============================================================
# STORE ID VALIDATION
# ============================================================

def validate_store_id(value) -> int:
    # Reject boolean
    if isinstance(value, bool):
        raise ValueError(
            "Store ID must contain only whole numbers. "
            "Letters and special characters are not allowed."
        )

    # If API receives string, allow only digits
    if isinstance(value, str):
        value = value.strip()

        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(
                "Store ID must contain only whole numbers. "
                "Letters and special characters are not allowed."
            )

        value = int(value)

    # Reject float, Decimal, etc.
    if not isinstance(value, int):
        raise ValueError(
            "Store ID must contain only whole numbers. "
            "Letters and special characters are not allowed."
        )

    if value <= 0:
        raise ValueError(
            "Store ID must be greater than 0."
        )

    return value


# ============================================================
# AMOUNT VALIDATION
# ============================================================

def validate_amount(value) -> Decimal:

    if isinstance(value, bool):
        raise ValueError(
            "Amount must contain only numbers. "
            "Letters and special characters are not allowed."
        )

    # Validate string before Decimal conversion
    if isinstance(value, str):
        value = value.strip()

        if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value):
            raise ValueError(
                "Amount must contain only numbers with up to "
                "2 decimal places. Letters and special characters "
                "are not allowed."
            )

        value = Decimal(value)

    elif isinstance(value, (int, float, Decimal)):
        value = Decimal(str(value))

    else:
        raise ValueError(
            "Amount must contain only numbers. "
            "Letters and special characters are not allowed."
        )

    if value <= 0:
        raise ValueError(
            "Expense amount must be greater than 0."
        )

    if value > Decimal("9999999999.99"):
        raise ValueError(
            "Expense amount cannot exceed 9,999,999,999.99."
        )

    # Maximum 2 decimal places
    if value.as_tuple().exponent < -2:
        raise ValueError(
            "Amount must not have more than 2 decimal places."
        )

    return value


# ============================================================
# CATEGORY VALIDATION
# ============================================================

def validate_category(value: str) -> str:

    if not isinstance(value, str):
        raise ValueError(
            "Category must contain only letters and spaces."
        )

    value = value.strip()

    if not value:
        raise ValueError(
            "Expense category cannot be empty."
        )

    if len(value) < 2:
        raise ValueError(
            "Expense category must contain at least 2 characters."
        )

    if len(value) > 100:
        raise ValueError(
            "Expense category must not exceed 100 characters."
        )

    # Only English letters and single spaces
    #
    # Valid:
    # Electricity
    # Office Supplies
    # Travel Expense
    #
    # Invalid:
    # Food123
    # Food@
    # Food-Supply
    # Office  Supplies
    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
        raise ValueError(
            "Category must contain only letters with a single "
            "space between words. Numbers and special characters "
            "are not allowed."
        )

    return value

# ============================================================
# DESCRIPTION VALIDATION
# ============================================================

def validate_description(value: str) -> str:

    if not isinstance(value, str):
        raise ValueError(
            "Description must contain only letters, numbers, and spaces."
        )

    value = value.strip()

    if not value:
        raise ValueError(
            "Description cannot be empty."
        )

    if len(value) < 3:
        raise ValueError(
            "Description must contain at least 3 characters."
        )

    if len(value) > 500:
        raise ValueError(
            "Description must not exceed 500 characters."
        )

    # Only English letters, numbers and spaces
    #
    # Valid:
    # Office Rent
    # Office Rent 5000
    # Electricity Bill 2026
    #
    # Invalid:
    # Office@Rent
    # Rent-5000
    # Bill#123
    if not re.fullmatch(r"[A-Za-z0-9]+(?: [A-Za-z0-9]+)*", value):
        raise ValueError(
            "Description can contain only letters, numbers, "
            "and spaces. Special characters are not allowed."
        )

    return value


# ============================================================
# EXPENSE DATE VALIDATION
# ============================================================

def validate_expense_date(value) -> date:

    # API input must be string in YYYY-MM-DD format
    if isinstance(value, str):

        value = value.strip()

        # Only YYYY-MM-DD
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(
                "Expense date must be in YYYY-MM-DD format. "
                "Letters and other special characters are not allowed."
            )

        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise ValueError(
                "Invalid expense date. Please enter a valid date "
                "in YYYY-MM-DD format."
            )

    elif not isinstance(value, date):
        raise ValueError(
            "Expense date must be in YYYY-MM-DD format."
        )

    if value > date.today():
        raise ValueError(
            "Expense date cannot be in the future."
        )

    return value

# ============================================================
# PAYMENT METHOD VALIDATION
# ============================================================

def validate_payment_method(value) -> str:

    if not isinstance(value, str):
        raise ValueError(
            "Payment method must be one of: cash, card, upi, "
            "bank_transfer, cheque, other."
        )

    value = value.strip().lower()

    allowed_methods = {
        "cash",
        "card",
        "upi",
        "bank_transfer",
        "cheque",
        "other",
    }

    if value not in allowed_methods:
        raise ValueError(
            "Payment method must be one of: cash, card, upi, "
            "bank_transfer, cheque, other."
        )

    return value


# ============================================================
# REFERENCE NUMBER VALIDATION
# ============================================================

def validate_reference_number(
    value: Optional[str],
) -> Optional[str]:

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            "Reference number must be text."
        )

    value = value.strip()

    if not value:
        return None

    if len(value) > 100:
        raise ValueError(
            "Reference number must not exceed 100 characters."
        )

    # Valid:
    # INV123
    # INV-123
    # INV/123
    # INV_123
    #
    # Invalid:
    # INV@123
    # INV 123
    # -INV123
    # INV-123-
    if not re.fullmatch(
        r"[A-Za-z0-9]+(?:[-/_][A-Za-z0-9]+)*",
        value,
    ):
        raise ValueError(
            "Reference number can contain only letters, numbers, "
            "hyphens, underscores, and slashes."
        )

    return value

# ============================================================
# CREATE STORE EXPENSE
# ============================================================

class StoreExpenseCreate(BaseModel):

    store_id: StrictInt = Field(
        ...,
        description="ID of the store where the expense occurred",
    )

    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Expense amount",
    )

    category: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Expense category",
    )

    description: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Description of the expense",
    )

    expense_date: date = Field(
        ...,
        description="Date on which the expense occurred",
    )

    payment_method: PaymentMethod = Field(
        ...,
        description="Payment method used for the expense",
    )

    reference_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional invoice, receipt, or reference number",
    )

    @field_validator("store_id", mode="before")
    @classmethod
    def validate_store_id_field(cls, value):
        return validate_store_id(value)

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount_field(cls, value):
        return validate_amount(value)

    @field_validator("category", mode="before")
    @classmethod
    def validate_category_field(cls, value):
        return validate_category(value)

    @field_validator("description", mode="before")
    @classmethod
    def validate_description_field(cls, value):
        return validate_description(value)

    @field_validator("expense_date", mode="before")
    @classmethod
    def validate_expense_date_field(cls, value):
        return validate_expense_date(value)

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method_field(cls, value):
        return validate_payment_method(value)

    @field_validator("reference_number", mode="before")
    @classmethod
    def validate_reference_number_field(cls, value):
        return validate_reference_number(value)

# ============================================================
# UPDATE STORE EXPENSE
# ============================================================

class StoreExpenseUpdate(BaseModel):

    store_id: Optional[StrictInt] = Field(
        default=None,
        description="ID of the store",
    )

    amount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Expense amount",
    )

    category: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Expense category",
    )

    description: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Description of the expense",
    )

    expense_date: Optional[date] = Field(
        default=None,
        description="Date on which the expense occurred",
    )

    payment_method: Optional[PaymentMethod] = Field(
        default=None,
        description="Payment method used for the expense",
    )

    reference_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional invoice, receipt, or reference number",
    )

    @field_validator("store_id", mode="before")
    @classmethod
    def validate_store_id_field(cls, value):
        if value is None:
            return None
        return validate_store_id(value)

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount_field(cls, value):
        if value is None:
            return None
        return validate_amount(value)

    @field_validator("category", mode="before")
    @classmethod
    def validate_category_field(cls, value):
        if value is None:
            return None
        return validate_category(value)

    @field_validator("description", mode="before")
    @classmethod
    def validate_description_field(cls, value):
        if value is None:
            return None
        return validate_description(value)

    @field_validator("expense_date", mode="before")
    @classmethod
    def validate_expense_date_field(cls, value):
        if value is None:
            return None
        return validate_expense_date(value)

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method_field(cls, value):
        if value is None:
            return None
        return validate_payment_method(value)

    @field_validator("reference_number", mode="before")
    @classmethod
    def validate_reference_number_field(cls, value):
        return validate_reference_number(value)

# ============================================================
# RESPONSE
# ============================================================

class StoreExpenseResponse(BaseModel):

    id: int
    store_id: int
    amount: Decimal
    category: str
    description: str
    expense_date: date
    payment_method: PaymentMethod
    reference_number: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True
    )
# ============================================================
# SUMMARY
# ============================================================

class StoreExpenseSummary(BaseModel):

    total_expenses: Decimal
    expense_count: int
