
from datetime import date, datetime
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
    model_validator,
    field_serializer,
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
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            "Store ID must contain only whole numbers. "
            "Letters, decimals and special characters are not allowed."
        )

    if value <= 0:
        raise ValueError("Store ID must be greater than 0.")

    return value


# ============================================================
# AMOUNT VALIDATION
# ============================================================

def validate_amount(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(
        value, (int, float, Decimal)
    ):
        raise ValueError("Amount must be a valid number.")

    try:
        value = Decimal(str(value))
    except Exception:
        raise ValueError("Amount must contain only numbers.")

    if not value.is_finite():
        raise ValueError("Amount must be a finite number.")

    if value <= 0:
        raise ValueError("Expense amount must be greater than 0.")

    if value > Decimal("9999999999.99"):
        raise ValueError(
            "Expense amount cannot exceed 9,999,999,999.99."
        )

    if value.as_tuple().exponent < -2:
        raise ValueError(
            "Amount must not have more than 2 decimal places."
        )

    return value


# ============================================================
# CATEGORY VALIDATION
# ============================================================

VALID_EXPENSE_CATEGORIES = {
    "Rent",
    "Utilities",
    "Salary",
    "Maintenance",
    "Travel",
    "Office Supplies",
    "Office",
    "Marketing",
    "Other",
}

CATEGORY_ALIASES = {
    "electricity": "Utilities",
    "utility": "Utilities",
    "travel expense": "Travel",
    "salaries": "Salary",
    "others": "Other",
}


def validate_category(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Category must contain only letters and spaces.")

    value = value.strip()

    if not value:
        raise ValueError("Expense category cannot be empty.")

    if len(value) < 2:
        raise ValueError(
            "Expense category must contain at least 2 characters."
        )

    if len(value) > 100:
        raise ValueError(
            "Expense category must not exceed 100 characters."
        )

    if not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):
        raise ValueError(
            "Category must contain only letters with single spaces "
            "between words. Numbers and special characters are not allowed."
        )

    normalized = value.lower()

    for canonical in VALID_EXPENSE_CATEGORIES:
        if canonical.lower() == normalized:
            return canonical

    if normalized in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[normalized]

    allowed = ", ".join(sorted(VALID_EXPENSE_CATEGORIES))
    raise ValueError(
        f"Invalid category '{value}'. Category must be one of: {allowed}."
    )


# ============================================================
# DESCRIPTION VALIDATION
# ============================================================

def validate_description(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Description must be a valid text value.")

    value = value.strip()

    if not value:
        raise ValueError("Description cannot be empty.")

    if len(value) < 3:
        raise ValueError(
            "Description must contain at least 3 characters."
        )

    if len(value) > 500:
        raise ValueError("Description cannot exceed 500 characters.")

    if not re.search(r"[A-Za-z]", value):
        raise ValueError(
            "Description must contain at least one letter."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9]+(?:[ .,'()/&-][A-Za-z0-9]+)*",
        value,
    ):
        raise ValueError(
            "Description can contain letters, numbers, and valid "
            "separators only. Special characters are not allowed."
        )

    return value


# ============================================================
# EXPENSE DATE VALIDATION
# ============================================================

def validate_expense_date(value):
    if isinstance(value, datetime):
        raise ValueError("Expense date must be in YYYY-MM-DD format.")

    if isinstance(value, date):
        parsed_date = value
    elif isinstance(value, str):
        value = value.strip()

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(
                "Expense date must be in YYYY-MM-DD format."
            )

        try:
            parsed_date = date.fromisoformat(value)
        except ValueError:
            raise ValueError(
                "Expense date must be a valid calendar date "
                "in YYYY-MM-DD format."
            )
    else:
        raise ValueError("Expense date must be in YYYY-MM-DD format.")

    if parsed_date > date.today():
        raise ValueError("Expense date cannot be in the future.")

    return parsed_date


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
    allowed = {
        "cash", "card", "upi", "bank_transfer", "cheque", "other"
    }

    if value not in allowed:
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
        raise ValueError("Reference number must be a text value.")

    value = value.strip()

    if not value:
        return None

    if value.lower() == "string":
        raise ValueError(
            "Reference number cannot be the placeholder 'string'."
        )

    if len(value) < 3:
        raise ValueError(
            "Reference number must contain at least 3 characters."
        )

    if len(value) > 100:
        raise ValueError(
            "Reference number cannot exceed 100 characters."
        )

    if not re.search(r"[A-Za-z]", value):
        raise ValueError(
            "Reference number must contain at least one letter."
        )

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
# EXTRACT DATE FROM REFERENCE NUMBER
# ============================================================

def extract_date_from_reference_number(
    ref: str,
) -> tuple[Optional[date], Optional[int]]:
    """
    Extract a date or year from reference_number if present.

    Supported formats:
    YYYY-MM-DD
    YYYY/MM/DD
    YYYY_MM_DD
    DD-MM-YYYY
    DD/MM/YYYY
    DD_MM_YYYY
    YYYYMMDD
    DDMMYYYY
    YYYY
    """

    # 1. YYYY-MM-DD / YYYY/MM/DD / YYYY_MM_DD
    m = re.search(
        r"\b(20\d{2})[-/_](0[1-9]|1[0-2])[-/_]"
        r"(0[1-9]|[12]\d|3[01])\b",
        ref,
    )

    if m:
        try:
            return (
                date(
                    int(m.group(1)),
                    int(m.group(2)),
                    int(m.group(3)),
                ),
                int(m.group(1)),
            )
        except ValueError:
            pass

    # 2. DD-MM-YYYY / DD/MM/YYYY / DD_MM_YYYY
    m = re.search(
        r"\b(0[1-9]|[12]\d|3[01])[-/_]"
        r"(0[1-9]|1[0-2])[-/_](20\d{2})\b",
        ref,
    )

    if m:
        try:
            return (
                date(
                    int(m.group(3)),
                    int(m.group(2)),
                    int(m.group(1)),
                ),
                int(m.group(3)),
            )
        except ValueError:
            pass

    # 3. YYYYMMDD
    for m in re.finditer(
        r"(?<!\d)"
        r"(20\d{2})"
        r"(0[1-9]|1[0-2])"
        r"(0[1-9]|[12]\d|3[01])"
        r"(?!\d)",
        ref,
    ):
        try:
            return (
                date(
                    int(m.group(1)),
                    int(m.group(2)),
                    int(m.group(3)),
                ),
                int(m.group(1)),
            )
        except ValueError:
            pass

    # 4. DDMMYYYY
    for m in re.finditer(
        r"(?<!\d)"
        r"(0[1-9]|[12]\d|3[01])"
        r"(0[1-9]|1[0-2])"
        r"(20\d{2})"
        r"(?!\d)",
        ref,
    ):
        try:
            return (
                date(
                    int(m.group(3)),
                    int(m.group(2)),
                    int(m.group(1)),
                ),
                int(m.group(3)),
            )
        except ValueError:
            pass

    # 5. Four-digit year 2000-2099
    m = re.search(
        r"(?<!\d)(20\d{2})(?!\d)",
        ref,
    )

    if m:
        return None, int(m.group(1))

    return None, None


# ============================================================
# REFERENCE NUMBER / EXPENSE DATE VALIDATION
# ============================================================

def validate_reference_number_date(
    reference_number: Optional[str],
    expense_date: Optional[date],
) -> None:

    if not reference_number or not expense_date:
        return

    ref_date, ref_year = extract_date_from_reference_number(
        reference_number
    )

    if ref_date is not None:
        if ref_date != expense_date:
            raise ValueError(
                f"Reference number date ({ref_date}) does not match "
                f"expense date ({expense_date})."
            )

    elif ref_year is not None:
        if ref_year != expense_date.year:
            raise ValueError(
                f"Reference number year ({ref_year}) does not match "
                f"expense date year ({expense_date.year})."
            )


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
    category: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(
        default=None, min_length=3, max_length=500
    )
    expense_date: date
    payment_method: PaymentMethod
    reference_number: Optional[str] = Field(
        default=None, max_length=100
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

    @model_validator(mode="after")
    def validate_reference_with_expense_date(self):
        if self.reference_number and self.expense_date:
            validate_reference_number_date(
                self.reference_number,
                self.expense_date,
            )
        return self


# ============================================================
# UPDATE STORE EXPENSE
# ============================================================

class StoreExpenseUpdate(BaseModel):
    store_id: Optional[StrictInt] = Field(default=None)
    amount: Optional[Decimal] = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    category: Optional[str] = Field(
        default=None, min_length=2, max_length=100
    )
    description: Optional[str] = Field(
        default=None, min_length=3, max_length=500
    )
    expense_date: Optional[date] = None
    payment_method: Optional[PaymentMethod] = None
    reference_number: Optional[str] = Field(
        default=None, max_length=100
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

    @model_validator(mode="after")
    def validate_reference_with_expense_date(self):
        if self.reference_number and self.expense_date:
            validate_reference_number_date(
                self.reference_number,
                self.expense_date,
            )
        return self


# ============================================================
# RESPONSE
# ============================================================

class StoreExpenseResponse(BaseModel):
    id: int
    store_id: int
    store_name: Optional[str] = None
    amount: Decimal
    category: str
    description: Optional[str] = None
    expense_date: date
    payment_method: PaymentMethod
    reference_number: Optional[str] = None
    status: Optional[str] = "active"
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None

    @field_serializer("amount", mode="plain")
    def serialize_amount(self, v: Decimal) -> float:
        return round(float(v), 2)

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# SUMMARY & ANALYTICS SCHEMAS
# ============================================================

class StoreExpenseSummary(BaseModel):
    total_expenses: Decimal
    expense_count: int


class CategoryExpenseStat(BaseModel):
    category: str
    total_amount: Decimal
    percentage: float
    count: int

    @field_serializer("total_amount", mode="plain")
    def serialize_amount(self, v: Decimal) -> str:
        return f"{Decimal(str(v)):.2f}"


class PaymentMethodExpenseStat(BaseModel):
    payment_method: str
    total_amount: Decimal
    percentage: float
    count: int

    @field_serializer("total_amount", mode="plain")
    def serialize_amount(self, v: Decimal) -> str:
        return f"{Decimal(str(v)):.2f}"


class StoreExpenseComparisonStat(BaseModel):
    store_id: int
    store_name: str
    total_amount: Decimal
    percentage: float
    count: int

    @field_serializer("total_amount", mode="plain")
    def serialize_amount(self, v: Decimal) -> str:
        return f"{Decimal(str(v)):.2f}"


class StoreExpenseAnalyticsSummary(BaseModel):
    total_expenses: Decimal
    total_count: int
    cash_expenses: Decimal
    digital_expenses: Decimal
    categories_breakdown: list[CategoryExpenseStat] = []
    payment_methods_breakdown: list[PaymentMethodExpenseStat] = []
    store_comparison: list[StoreExpenseComparisonStat] = []
    recent_expenses: list[StoreExpenseResponse] = []

    @field_serializer("total_expenses", "cash_expenses", "digital_expenses", mode="plain")
    def serialize_amount(self, v: Decimal) -> str:
        return f"{Decimal(str(v)):.2f}"


# ============================================================
# DAILY REPORT SCHEMAS
# ============================================================

class StoreExpenseDailyReportResponse(BaseModel):
    report_date: date
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    total_expenses: Decimal
    total_count: int
    cash_expense_total: Decimal
    non_cash_expense_total: Decimal
    cash_drawer_payout_count: int
    expenses: list[StoreExpenseResponse] = []

    @field_serializer("total_expenses", "cash_expense_total", "non_cash_expense_total", mode="plain")
    def serialize_amount(self, v: Decimal) -> str:
        return f"{Decimal(str(v)):.2f}"
