from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

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

def validate_store_id(value) -> int:
    if isinstance(value, bool):
        raise ValueError(
            "Store ID must be a whole number (integer). "
            "Only integer values are accepted. Example: 1"
        )

    if not isinstance(value, int):
        raise ValueError(
            "Store ID must be a whole number (integer). "
            "Only integer values are accepted. Example: 1"
        )

    if value <= 0:
        raise ValueError(
            "Store ID must be greater than 0."
        )

    return value


def validate_amount(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError(
            "Expense amount must be greater than 0."
        )

    if value > Decimal("9999999999.99"):
        raise ValueError(
            "Expense amount cannot exceed 9,999,999,999.99."
        )

    return value


def validate_category(value: str) -> str:
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

    if not all(char.isalpha() or char.isspace() for char in value):
        raise ValueError(
            "Expense category must contain only letters and spaces."
        )

    return value


def validate_description(value: str) -> str:
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

    return value


def validate_expense_date(value: date) -> date:
    if value > date.today():
        raise ValueError(
            "Expense date cannot be in the future."
        )

    return value


def validate_reference_number(
    value: Optional[str],
) -> Optional[str]:

    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    if len(value) > 100:
        raise ValueError(
            "Reference number must not exceed 100 characters."
        )

    if not all(
        char.isalnum() or char == "-"
        for char in value
    ):
        raise ValueError(
            "Reference number can contain only "
            "letters, numbers, and hyphens."
        )

    return value

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

    @field_validator("amount")
    @classmethod
    def validate_amount_field(cls, value: Decimal) -> Decimal:
        return validate_amount(value)

    @field_validator("category")
    @classmethod
    def validate_category_field(cls, value: str) -> str:
        return validate_category(value)

    @field_validator("description")
    @classmethod
    def validate_description_field(cls, value: str) -> str:
        return validate_description(value)

    @field_validator("expense_date")
    @classmethod
    def validate_expense_date_field(cls, value: date) -> date:
        return validate_expense_date(value)

    @field_validator("reference_number")
    @classmethod
    def validate_reference_number_field(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        return validate_reference_number(value)


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

    @field_validator("amount")
    @classmethod
    def validate_amount_field(
        cls,
        value: Optional[Decimal],
    ) -> Optional[Decimal]:
        if value is None:
            return None

        return validate_amount(value)

    @field_validator("category")
    @classmethod
    def validate_category_field(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        return validate_category(value)

    @field_validator("description")
    @classmethod
    def validate_description_field(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        return validate_description(value)

    @field_validator("expense_date")
    @classmethod
    def validate_expense_date_field(
        cls,
        value: Optional[date],
    ) -> Optional[date]:
        if value is None:
            return None

        return validate_expense_date(value)

    @field_validator("reference_number")
    @classmethod
    def validate_reference_number_field(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        return validate_reference_number(value)



class StoreExpenseResponse(BaseModel):
    id: int
    store_id: int
    amount: Decimal
    category: str
    description: str
    expense_date: date
    payment_method: PaymentMethod
    reference_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StoreExpenseSummary(BaseModel):
    total_expenses: Decimal
    expense_count: int