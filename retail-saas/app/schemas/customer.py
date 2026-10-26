from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Literal, Any
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from app.schemas.order import OrderResponse
from app.utils.validators import validate_email_address, validate_gstin_number


class CustomerExportStatus(str, Enum):
    all = "all"
    active = "active"
    inactive = "inactive"


class CustomerExportFormat(str, Enum):
    excel = "excel"
    pdf = "pdf"


def validate_phone_number(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Phone number must be a string")

    v = v.strip()

    if not v:
        raise ValueError("Phone number cannot be empty or whitespace")

    if not re.fullmatch(r"^(?:\+91)?[6-9]\d{9}$", v):
        raise ValueError(
            "Phone number must be 10 digits starting with 6-9, "
            "or +91 followed by 10 digits starting with 6-9"
        )

    core_digits = v[3:] if v.startswith("+91") else v

    # Reject full sequential / serial numbers (e.g. 9876543210, 6789012345, 8765432109)
    ascending_seq = "01234567890123456789"
    descending_seq = "98765432109876543210"
    if core_digits in descending_seq or core_digits in ascending_seq:
        raise ValueError("Phone number cannot be a sequential serial number")

    # Reject 7 or more consecutive ascending or descending sequential digits (e.g. 9123456789, 9876543200)
    for i in range(len(core_digits) - 6):
        sub = core_digits[i:i+7]
        if sub in "0123456789" or sub in "9876543210":
            raise ValueError("Phone number cannot contain sequential serial digits")

    # Reject identical repeated digits (e.g. 9999999999, 8888888888, 7777777777, 6666666666)
    if len(set(core_digits)) == 1:
        raise ValueError("Phone number cannot consist of identical repeated digits")

    # Reject repetitive dummy digits where remaining 9 digits are identical (e.g. 9000000000, 8000000000, 7000000000, 6000000000, 9111111111)
    if len(set(core_digits[1:])) == 1:
        raise ValueError("Phone number cannot consist of repetitive dummy digits")

    # Reject 5 or more consecutive identical digits (e.g. 9800000123, 9999912345)
    if re.search(r"(\d)\1{4,}", core_digits):
        raise ValueError("Phone number cannot contain 5 or more consecutive identical digits")

    # Reject ending with multiple dummy zeros (e.g. 9876500000, 9123400000)
    if core_digits.endswith("00000"):
        raise ValueError("Phone number cannot end with multiple dummy zeros")

    return v


def validate_customer_name(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Name must be a string")

    v = v.strip()

    if len(v) < 2 or len(v) > 255:
        raise ValueError("Name must be between 2 and 255 characters")

    if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
        raise ValueError(f"Name cannot be placeholder '{v}'")

    if not any(c.isalpha() for c in v):
        raise ValueError(
            "Name must contain at least one alphabetic character"
        )

    if v.isdigit():
        raise ValueError("Name cannot consist only of digits")

    alpha_count = sum(1 for c in v if c.isalpha())

    if alpha_count < 2:
        raise ValueError(
            "Name must contain at least two alphabetic characters"
        )

    for c in v:
        if not (c.isalpha() or c in " '-."):
            raise ValueError(
                "Name contains invalid characters. Only letters, spaces, "
                "apostrophes, hyphens, and periods are allowed"
            )

    return v


CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS = {
    "string", "null", "none", "undefined", "test", "dummy", "sample",
    "placeholder", "name", "description", "unknown", "n/a", "na",
    "temp", "false", "true", "p0@#$", "ppppp", "123445"
}

CUSTOMER_FORBIDDEN_TEXT_SYMBOLS = set(r"\|[]{}<>~^")


def validate_meaningful_text(
    v: Optional[str],
    field_name: str = "Field",
    min_length: int = 1,
    max_length: int = 2000,
    required: bool = True,
) -> Optional[str]:

    if v is None:
        if required:
            raise ValueError(f"{field_name} cannot be null")
        return None

    if not isinstance(v, str):
        raise ValueError(f"{field_name} must be a string")

    v = v.strip()

    if not v:
        if required:
            raise ValueError(
                f"{field_name} cannot be empty or whitespace"
            )
        return None

    if len(v) < min_length or len(v) > max_length:
        raise ValueError(
            f"{field_name} must be between "
            f"{min_length} and {max_length} characters"
        )

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
        raise ValueError(
            f"{field_name} cannot be placeholder '{v}'"
        )

    if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v):
        raise ValueError(f"{field_name} contains invalid special characters")

    if re.search(r"[-+@#*/=_]{2,}", v):
        raise ValueError(f"{field_name} cannot contain consecutive repeating symbols")

    dangerous_patterns = [
        r"<\s*script",
        r"<\s*/\s*script",
        r"<\s*iframe",
        r"<\s*style",
        r"javascript\s*:",
        r"onload\s*=",
        r"onerror\s*=",
        r"<\s*img",
        r"<\s*a\s+",
        r"alert\s*\(",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, v, re.IGNORECASE):
            raise ValueError(
                f"{field_name} contains invalid or dangerous "
                "HTML/script content"
            )

    if "<" in v and ">" in v:
        raise ValueError(
            f"HTML tags are not allowed in {field_name.lower()}"
        )

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    alpha_count = len(alpha_chars)

    if alpha_count == 0:
        if v.isdigit():
            raise ValueError(
                f"{field_name} cannot be numeric-only"
            )

        raise ValueError(
            f"{field_name} must contain meaningful text with letters, "
            "not only numbers or symbols"
        )

    if len(alpha_chars) >= 2 and len(set(alpha_chars)) < 2:
        raise ValueError(
            f"{field_name} cannot consist of repetitive characters '{v}'"
        )

    return v


def validate_address(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    v = v.strip()

    if not v:
        raise ValueError(
            "Address cannot be empty or whitespace"
        )

    if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
        raise ValueError(f"Address cannot be placeholder '{v}'")

    return v


def validate_birthday(v: Optional[date]) -> Optional[date]:
    if v is None:
        return None

    if v > date.today():
        raise ValueError(
            "Birthday cannot be in the future"
        )

    return v

class SubResourceNoDataResponse(BaseModel):
    success: bool = True
    message: str
    data: list = Field(default_factory=list)

class CustomerOrdersResponse(BaseModel):
    success: bool = True
    message: str
    customer_id: int
    orders: list[OrderResponse] = Field(default_factory=list)
    data: list[OrderResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class CustomerBase(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=255,
        description="Name must be 2 to 255 characters",
    )

    email: Optional[EmailStr] = None

    phone: str = Field(
        description="Phone must be 10 digits or +91 followed by 10 digits"
    )

    address: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
    )

    birthday: Optional[date] = None

    whatsapp_opt_in: StrictBool = True
    sms_opt_in: StrictBool = True

    @field_validator("whatsapp_opt_in", "sms_opt_in", mode="before")
    @classmethod
    def validate_opt_in_bool(cls, v: Any, info) -> Any:
        if v is None or not isinstance(v, bool):
            raise ValueError(f"Invalid value for {info.field_name}. Expected a boolean: true or false.")
        return v

    status: Literal[
        "active",
        "inactive",
        "blocked"
    ] = "active"

    segment: Literal[
        "new",
        "regular",
        "vip",
        "inactive"
    ] = "new"

    credit_limit: Optional[Decimal] = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    outstanding_balance: Optional[Decimal] = Field(default=Decimal("0.00"))

    @field_validator("email", mode="before")
    @classmethod
    def validate_customer_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Customer email must be a string")
        v_str = v.strip()
        if not v_str:
            return None
        if any(c.isupper() for c in v_str):
            raise ValueError("Customer email must contain lowercase letters only")
        return validate_email_address(v_str, field_name="Customer email", required=False)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return validate_phone_number(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return validate_customer_name(v)

    @field_validator("address")
    @classmethod
    def check_address(
        cls,
        v: Optional[str]
    ) -> Optional[str]:
        return validate_address(v)

    @field_validator("birthday")
    @classmethod
    def check_birthday(
        cls,
        v: Optional[date]
    ) -> Optional[date]:
        return validate_birthday(v)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(
        cls,
        v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return None
        return validate_gstin_number(v, field_name="GSTIN", required=False)


class CustomerCreate(CustomerBase):

    address: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Address is optional",
    )

    birthday: Optional[date] = Field(
        default=None,
        description=(
            "Customer birthday is optional "
            "and cannot be in the future"
        ),
    )

    @field_validator("address", mode="before")
    @classmethod
    def check_create_address_before(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                raise ValueError(
                    "Address cannot be empty or whitespace"
                )
            if v_strip.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
                raise ValueError(
                    f"Address cannot be placeholder '{v}'"
                )
            return v_strip

        return v

    @field_validator("birthday", mode="before")
    @classmethod
    def check_create_birthday_before(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            if v_strip.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
                raise ValueError(
                    f"Birthday cannot be placeholder '{v}'"
                )
            return v_strip

        return v

    @field_validator("birthday")
    @classmethod
    def validate_create_birthday(
        cls,
        value: Optional[date],
    ) -> Optional[date]:
        return validate_birthday(value)


class CustomerUpdate(BaseModel):

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    email: Optional[EmailStr] = None

    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=13,
        description=(
            "Phone must be 10 digits or "
            "+91 followed by 10 digits"
        ),
    )

    address: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
    )

    birthday: Optional[date] = None

    whatsapp_opt_in: Optional[StrictBool] = None
    sms_opt_in: Optional[StrictBool] = None

    @field_validator("whatsapp_opt_in", "sms_opt_in", mode="before")
    @classmethod
    def validate_update_opt_in_bool(cls, v: Any, info) -> Any:
        if v is None or not isinstance(v, bool):
            raise ValueError(f"Invalid value for {info.field_name}. Expected a boolean: true or false.")
        return v
    credit_limit: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))

    @field_validator("name", mode="before")
    @classmethod
    def check_update_name_before(cls, v):

        if v is None:
            raise ValueError(
                "Name cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Name must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Name cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Name cannot be placeholder '{v}'"
            )

        return v

    @field_validator("name")
    @classmethod
    def check_name(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_customer_name(v)

    @field_validator("phone", mode="before")
    @classmethod
    def check_update_phone_before(cls, v):

        if v is None:
            raise ValueError(
                "Phone cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Phone must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Phone cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Phone cannot be placeholder '{v}'"
            )

        return v

    @field_validator("phone")
    @classmethod
    def check_phone(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_phone_number(v)

    @field_validator("address", mode="before")
    @classmethod
    def check_update_address_before(cls, v):

        if v is None:
            raise ValueError(
                "Address cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Address must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Address cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Address cannot be placeholder '{v}'"
            )

        return v

    @field_validator("address")
    @classmethod
    def check_address(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_address(v)

    @field_validator("birthday", mode="before")
    @classmethod
    def check_update_birthday_before(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            if v_strip.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
                raise ValueError(
                    f"Birthday cannot be placeholder '{v}'"
                )
            return v_strip

        return v

    @field_validator("birthday")
    @classmethod
    def check_birthday(
        cls,
        v: Optional[date]
    ) -> Optional[date]:

        if v is None:
            return None

        return validate_birthday(v)

    @field_validator("email", mode="before")
    @classmethod
    def check_update_email_before(cls, v):

        if v is None:
            raise ValueError(
                "Email cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "Email must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "Email cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"Email cannot be placeholder '{v}'"
            )

        if any(c.isupper() for c in v):
            raise ValueError(
                "Customer email must contain lowercase letters only"
            )

        return validate_email_address(v, field_name="Customer email", required=True)

    @field_validator("gstin", mode="before")
    @classmethod
    def check_update_gstin_before(cls, v):

        if v is None:
            raise ValueError(
                "GSTIN cannot be null"
            )

        if not isinstance(v, str):
            raise ValueError(
                "GSTIN must be a string"
            )

        v = v.strip()

        if not v:
            raise ValueError(
                "GSTIN cannot be empty or whitespace"
            )

        if v.lower() in {"string", "null", "none", "undefined", "-----", "@#$%%"}:
            raise ValueError(
                f"GSTIN cannot be placeholder '{v}'"
            )

        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(
        cls,
        v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return None
        return validate_gstin_number(v, field_name="GSTIN", required=False)


class CustomerResponse(CustomerBase):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    tenant_id: int
    loyalty_points: Optional[int] = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("status", mode="before")
    @classmethod
    def sanitize_status(cls, v):

        if v is None or not str(v).strip():
            return "active"

        s = str(v).strip().lower()
        if s in ("active", "inactive", "blocked"):
            return s

        return v

    @field_validator("segment", mode="before")
    @classmethod
    def sanitize_segment(cls, v):

        if v is None or not str(v).strip():
            return "new"

        s = str(v).strip().lower()
        if s in ("new", "regular", "vip", "inactive"):
            return s

        return v

    @field_validator("email", mode="before")
    @classmethod
    def sanitize_email(cls, v):

        if v is None or not str(v).strip():
            return None

        s = str(v).strip()

        return s if ("@" in s and "." in s) else None

    @field_validator("gstin", mode="before")
    @classmethod
    def sanitize_gstin(cls, v):

        if v is None or not str(v).strip():
            return None

        return str(v).strip().upper()

    @field_validator("phone", mode="before")
    @classmethod
    def sanitize_phone(cls, v):

        if v is None:
            return ""

        return str(v).strip()


class MessageResponse(BaseModel):
    message: str


class CustomerStatsResponse(BaseModel):
    total_customers: int
    active_customers: int
    inactive_customers: Optional[int] = 0
    blocked_customers: Optional[int] = 0
    new_customers: Optional[int] = 0
    regular_customers: Optional[int] = 0
    vip_customers: Optional[int] = 0
    total_revenue: Optional[int] = 0
    new_this_month: Optional[int] = 0

class CustomerFeedbackCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    invoice_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    rating: int = Field(
        ge=1,
        le=5
    )

    comments: Optional[str] = Field(
        default=None,
        max_length=2000
    )

    suggestions: Optional[str] = Field(
        default=None,
        max_length=2000
    )

    feedback: Optional[str] = Field(
        default=None,
        max_length=2000
    )

    @field_validator("comments", "suggestions", "feedback", mode="before")
    @classmethod
    def clean_feedback_strings_before(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            return v_strip
        return v

    @field_validator("comments")
    @classmethod
    def validate_comments(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Comments",
            1,
            2000,
            required=False,
        )

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Suggestions",
            1,
            2000,
            required=False,
        )

    @field_validator("feedback")
    @classmethod
    def validate_feedback(
        cls,
        v: Optional[str]
    ) -> Optional[str]:

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Feedback",
            1,
            2000,
            required=False,
        )


class CustomerFeedbackResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    invoice_id: Optional[int] = None
    rating: int
    comments: Optional[str] = None
    suggestions: Optional[str] = None
    feedback: Optional[str] = None
    created_at: datetime

class WalletOperationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(
        gt=0,
        description="Customer ID must be a positive integer"
    )

    amount: Decimal = Field(
        gt=0,
        decimal_places=2,
        max_digits=12,
        description="Amount must be greater than zero"
    )

    reference_no: str = Field(
        min_length=3,
        max_length=30,
        description="Reference number (3 to 30 characters)"
    )

    remarks: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Remarks must be meaningful text without numbers (3 to 100 characters)"
    )

    @field_validator("reference_no", mode="before")
    @classmethod
    def validate_reference(cls, v: Any) -> str:
        if v is None:
            raise ValueError("Reference number is required and cannot be null")

        if not isinstance(v, str):
            raise ValueError("Reference number must be a string")

        v = v.strip()

        if not v:
            raise ValueError("Reference number cannot be empty or whitespace")

        if len(v) < 3 or len(v) > 30:
            raise ValueError("Reference number must be between 3 and 30 characters")

        if v.lower() in {"string", "null", "none", "undefined", "test", "dummy", "sample"}:
            raise ValueError(f"Reference number cannot be placeholder '{v}'")

        if not re.fullmatch(r"^[A-Za-z0-9_-]{3,30}$", v):
            raise ValueError("Reference number contains invalid characters (only alphanumeric, hyphens, and underscores allowed)")

        if not any(c.isdigit() for c in v):
            raise ValueError("Reference number cannot be alphabetic-only")

        # Reject all zeros, all same character repeated, or sequential dummy strings
        digits_only = "".join(c for c in v if c.isdigit())
        if digits_only and len(set(digits_only)) == 1 and len(digits_only) >= 5:
            raise ValueError("Reference number cannot be repeated identical digits")

        if re.fullmatch(r"^0+$", v) or (re.fullmatch(r"^[0_-]+$", v) and not any(c.isalpha() or c in '123456789' for c in v)):
            raise ValueError("Reference number cannot be zero or all zeros")

        return v

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        if not isinstance(v, str):
            raise ValueError("Remarks must be a string")

        v = v.strip()

        if not v:
            raise ValueError("Remarks cannot be empty or whitespace")

        if len(v) < 3 or len(v) > 100:
            raise ValueError("Remarks must be between 3 and 100 characters")

        # Reject numeric digits strictly in remarks per requirement
        if any(c.isdigit() for c in v):
            raise ValueError("Remarks cannot contain numeric digits")

        # Reject placeholders
        clean_norm = re.sub(r"[^a-zA-Z]", "", v.lower())
        if v.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
            raise ValueError(f"Remarks cannot be placeholder '{v}'")

        if v.lower() in {"na", "n/a", "nil", "none", "null", "test", "dummy", "sample"}:
            raise ValueError(f"Remarks cannot be placeholder '{v}'")

        # Reject forbidden special symbols
        if any(c in CUSTOMER_FORBIDDEN_TEXT_SYMBOLS for c in v):
            raise ValueError("Remarks contains invalid special characters")

        # Reject consecutive repeating symbols
        if re.search(r"[-+*/=_]{2,}", v):
            raise ValueError("Remarks cannot contain consecutive repeating symbols")

        # Require meaningful alphabetic words
        alpha_chars = [c.lower() for c in v if c.isalpha()]
        if len(alpha_chars) < 3:
            raise ValueError("Remarks must contain at least 3 letters")

        # Reject single character repeated (e.g. "aaaaa", "ppppp")
        if len(set(alpha_chars)) < 2:
            raise ValueError(f"Remarks cannot consist of repetitive characters '{v}'")

        # Reject keyboard smash / gibberish: any unbroken word longer than 25 characters
        words = v.split()
        for word in words:
            if len(word) > 25:
                raise ValueError("Remarks cannot contain excessively long unbroken words or random gibberish")

        return v


class WalletCreditRequest(WalletOperationBase):
    pass


class WalletDebitRequest(WalletOperationBase):
    pass


class WalletResponse(BaseModel):

    id: Optional[int] = None
    customer_id: int
    current_balance: Optional[float] = None
    balance: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )

    @model_validator(mode="after")
    def sync_balance(self):

        if (
            self.balance is None
            and self.current_balance is not None
        ):
            self.balance = Decimal(
                str(self.current_balance)
            )

        elif (
            self.current_balance is None
            and self.balance is not None
        ):
            self.current_balance = float(
                self.balance
            )

        return self


class WalletTransactionResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    wallet_id: Optional[int] = None
    customer_id: Optional[int] = None
    transaction_type: str
    amount: float
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    balance_after: Optional[Decimal] = None
    reason: Optional[str] = None
    created_at: datetime


class WalletOperationResponse(BaseModel):

    id: int
    customer_id: int
    amount: float
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    balance: float
    current_balance: Optional[float] = None

    model_config = ConfigDict(
        from_attributes=True
    )

class LoyaltyAddPointsRequest(BaseModel):
    points: int = Field(..., gt=0, le=10000, description="Loyalty points to add")


class LoyaltyEarnRequest(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    points: int = Field(
        gt=0
    )

    invoice_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    reason: str = Field(
        min_length=1,
        max_length=500
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str):

        return validate_meaningful_text(
            v,
            "Reason",
            1,
            500,
            required=True,
        )


class LoyaltyRedeemRequest(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    points: int = Field(
        gt=0
    )


class LoyaltyResponse(BaseModel):

    id: Optional[int] = None
    customer_id: int
    invoice_id: Optional[int] = None
    points_earned: Optional[int] = None
    points_redeemed: Optional[int] = None
    balance_points: Optional[int] = None
    points: Optional[int] = None
    expiry_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )

    @model_validator(mode="after")
    def sync_points(self):

        if (
            self.points is None
            and self.balance_points is not None
        ):
            self.points = self.balance_points

        elif (
            self.balance_points is None
            and self.points is not None
        ):
            self.balance_points = self.points

        return self

class CommunicationCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    channel: Optional[
        Literal["whatsapp", "sms", "email"]
    ] = None

    communication_type: Optional[
        Literal["SMS", "WHATSAPP", "EMAIL"]
    ] = None

    message: str = Field(
        min_length=1,
        max_length=5000
    )

    @field_validator(
        "communication_type",
        mode="before"
    )
    @classmethod
    def normalize_comm_type(cls, v):

        if isinstance(v, str):
            v = v.strip().upper()

        return v

    @field_validator(
        "channel",
        mode="before"
    )
    @classmethod
    def normalize_channel(cls, v):

        if isinstance(v, str):
            v = v.strip().lower()

        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str):

        return validate_meaningful_text(
            v,
            "Message",
            1,
            5000,
            required=True,
        )

    @model_validator(mode="after")
    def sync_communication_type(self):

        if (
            self.communication_type is None
            and self.channel is not None
        ):
            self.communication_type = (
                self.channel.upper()
            )

        if (
            self.channel is None
            and self.communication_type is not None
        ):
            self.channel = (
                self.communication_type.lower()
            )

        return self


class CommunicationResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    channel: Optional[str] = None
    communication_type: Optional[str] = None
    message: str
    status: Optional[str] = None
    delivery_status: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @model_validator(mode="after")
    def sync_channel_and_status(self):

        if (
            not self.channel
            and self.communication_type
        ):
            self.channel = self.communication_type

        if (
            not self.communication_type
            and self.channel
        ):
            self.communication_type = self.channel

        if (
            not self.status
            and self.delivery_status
        ):
            self.status = self.delivery_status

        if (
            not self.delivery_status
            and self.status
        ):
            self.delivery_status = self.status

        if (
            not self.sent_at
            and self.created_at
        ):
            self.sent_at = self.created_at

        return self

class ReferralCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    referred_customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    referral_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional custom referral code. If not provided, one is automatically generated."
    )

    @model_validator(mode="after")
    def validate_referral(self):

        if (
            self.customer_id is not None
            and self.referred_customer_id is not None
            and self.customer_id
            == self.referred_customer_id
        ):
            raise ValueError(
                "Customer cannot refer themselves"
            )

        return self


class ReferralResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    referral_code: Optional[str] = None
    referred_customer_id: Optional[int] = None
    reward_amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CustomerNoteCreate(BaseModel):

    customer_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    note: str = Field(
        min_length=5,
        max_length=5000,
        description="Meaningful note text (letters must exceed digits, no repeating ??)",
    )

    @field_validator("note")
    @classmethod
    def validate_note(cls, v: str):
        if v is None:
            raise ValueError("Note is required and cannot be null")

        if not isinstance(v, str):
            raise ValueError("Note must be a string")

        v = v.strip()

        if not v:
            raise ValueError("Note cannot be empty or whitespace")

        if len(v) < 5 or len(v) > 5000:
            raise ValueError("Note must be between 5 and 5000 characters")

        # Reject HTML or dangerous script injections
        dangerous_patterns = [
            r"<\s*script",
            r"<\s*/\s*script",
            r"<\s*iframe",
            r"<\s*style",
            r"javascript\s*:",
            r"onload\s*=",
            r"onerror\s*=",
            r"<\s*img",
            r"<\s*a\s+",
            r"alert\s*\(",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Note contains invalid or dangerous HTML/script content")

        if "<" in v and ">" in v:
            raise ValueError("HTML tags are not allowed in note")

        # Reject consecutive repeating question marks or punctuation (e.g. ????? from Image 2)
        if re.search(r"\?{2,}", v):
            raise ValueError("Note cannot contain consecutive repeating question marks")

        if re.search(r"!{3,}", v):
            raise ValueError("Note cannot contain consecutive repeating exclamation marks")

        if re.search(r"[-+*/=_]{3,}", v):
            raise ValueError("Note cannot contain consecutive repeating symbols")

        # Reject placeholder phrases or meta dummy text
        clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
        if v.lower() in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS or clean_norm in CUSTOMER_DISALLOWED_TEXT_PLACEHOLDERS:
            raise ValueError(f"Note cannot be placeholder '{v}'")

        clean_phrase = re.sub(r"[^a-zA-Z\s]", "", v.lower()).strip()
        clean_phrase = re.sub(r"\s+", " ", clean_phrase)
        disallowed_note_phrases = {
            "note is not required",
            "not required",
            "no note",
            "nothing",
            "test note",
            "dummy note",
            "sample note",
            "ordinary note",
        }
        if clean_phrase in disallowed_note_phrases:
            raise ValueError(f"Note cannot be placeholder or test phrase '{v}'")

        # Letter and digit checks (Image 1 fix)
        alpha_chars = [c.lower() for c in v if c.isalpha()]
        alpha_count = len(alpha_chars)
        digit_count = sum(1 for c in v if c.isdigit())

        if alpha_count < 3:
            raise ValueError("Note must contain meaningful text with at least 3 letters")

        # Digits must not dominate descriptive text (rejects 99% numerical/decimal spam)
        if digit_count >= alpha_count:
            raise ValueError("Note cannot contain more digits than letters or be dominated by numbers/decimals")

        # Reject long consecutive numeric sequences
        if re.search(r"\d{15,}", v):
            raise ValueError("Note cannot contain excessively long continuous number sequences")

        # Reject repetitive single character spam (e.g. "aaaaa", "ppppp")
        if len(set(alpha_chars)) < 2:
            raise ValueError(f"Note cannot consist of repetitive characters '{v}'")

        # Reject excessively long unbroken words, numbers, or gibberish (e.g. Image 1 token)
        words = v.split()
        if len(words) < 2 and len(v) > 20:
            raise ValueError("Note must contain at least 2 words")

        for word in words:
            if len(word) > 35:
                raise ValueError("Note cannot contain excessively long unbroken words, numbers, or random gibberish")

        return v


class CustomerNoteResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    customer_id: int
    note: str
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

class CampaignSendRequest(BaseModel):

    campaign_id: Optional[int] = Field(
        default=None,
        gt=0
    )

    channel: Optional[
        Literal["whatsapp", "sms", "email"]
    ] = None

    customer_ids: Optional[list[int]] = Field(
        default=None,
        min_length=1
    )

    communication_type: Optional[str] = None

    message: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=5000,
    )

    @field_validator("customer_ids")
    @classmethod
    def validate_customer_ids(
        cls,
        v: Optional[list[int]]
    ):

        if v is None:
            return None

        if not v:
            raise ValueError(
                "customer_ids cannot be empty"
            )

        for cid in v:
            if cid <= 0:
                raise ValueError(
                    "Customer IDs must be positive integers"
                )

        return v

    @field_validator(
        "communication_type",
        mode="before"
    )
    @classmethod
    def validate_comm_type(cls, v):

        if v is None:
            return None

        if isinstance(v, str):
            v = v.strip().upper()

        if v not in (
            "SMS",
            "WHATSAPP",
            "EMAIL"
        ):
            raise ValueError(
                "Invalid communication type. "
                "Allowed values: SMS, WHATSAPP, EMAIL"
            )

        return v

    @field_validator(
        "channel",
        mode="before"
    )
    @classmethod
    def normalize_channel(cls, v):

        if isinstance(v, str):
            v = v.strip().lower()

        return v

    @field_validator("message")
    @classmethod
    def validate_message(
        cls,
        v: Optional[str]
    ):

        if v is None:
            return None

        return validate_meaningful_text(
            v,
            "Message",
            1,
            5000,
            required=True,
        )

    @model_validator(mode="after")
    def sync_campaign_channel_and_type(self):

        if (
            self.communication_type is None
            and self.channel is not None
        ):
            self.communication_type = (
                self.channel.upper()
            )

        if (
            self.channel is None
            and self.communication_type is not None
        ):
            self.channel = (
                self.communication_type.lower()
            )

        return self


class CampaignSendResponse(BaseModel):

    campaign_id: Optional[int] = None
    sent_count: int
    failed_count: int
    message: str
    total_customers: Optional[int] = None


class TopCustomerResponse(BaseModel):

    id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    total_spend: Optional[float] = None
    loyalty_points: Optional[int] = None
    status: Optional[str] = None
    order_count: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class RetentionResponse(BaseModel):

    total_customers: int
    active_customers: Optional[int] = None
    inactive_customers: Optional[int] = None
    retained_customers: Optional[int] = None
    retention_rate: float


class LifetimeValueResponse(BaseModel):

    customer_id: int
    customer_name: str
    total_spend: Optional[float] = None
    loyalty_points: Optional[int] = None
    lifetime_value: Optional[Decimal] = None
    total_orders: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class LoyaltyReportResponse(BaseModel):

    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    points_earned: Optional[int] = None
    points_redeemed: Optional[int] = None
    balance_points: Optional[int] = None
    total_customers: Optional[int] = None
    total_points_earned: Optional[int] = None
    total_points_redeemed: Optional[int] = None
    total_points_balance: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class CustomerStatusUpdate(BaseModel):

    status: Literal[
        "active",
        "inactive",
        "blocked"
    ]


class CustomerListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[CustomerResponse] = Field(default_factory=list)


class CustomerReferralListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[ReferralResponse] = Field(default_factory=list)


class CustomerCommunicationListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[CommunicationResponse] = Field(default_factory=list)


class TopCustomerListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[TopCustomerResponse] = Field(default_factory=list)


class LifetimeValueListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[LifetimeValueResponse] = Field(default_factory=list)


class LoyaltyReportListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[LoyaltyReportResponse] = Field(default_factory=list)


class CreditLimitUpdateRequest(BaseModel):
    credit_limit: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("99999999.99"),
        description="Customer credit limit (must be non-negative)",
    )


class CustomerPaymentRequest(BaseModel):
    amount: Decimal = Field(
        ...,
        gt=Decimal("0.00"),
        le=Decimal("99999999.99"),
        description="Payment amount to credit against dues",
    )
    payment_method: str = Field(
        default="cash",
        description="Payment method: cash, upi, card, bank_transfer",
    )
    reference_no: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Transaction or payment reference number",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Payment remarks or invoice reference",
    )


class CustomerLedgerEntryResponse(BaseModel):
    id: int
    customer_id: int
    entry_type: str
    amount: Decimal
    balance_after: Decimal
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerLedgerStatementResponse(BaseModel):
    success: bool = True
    customer_id: int
    customer_name: str
    credit_limit: Decimal
    outstanding_balance: Decimal
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")
    entries: list[CustomerLedgerEntryResponse] = Field(default_factory=list)


class FeedbackAnalyticsResponse(BaseModel):
    success: bool = True
    total_feedbacks: int
    average_rating: float
    rating_breakdown: dict[str, int]
    nps_score: float


class CustomerDeleteResponse(BaseModel):
    success: bool = True
    message: str
    customer_id: int


class SendLedgerPdfResponse(BaseModel):
    success: bool = True
    message: str
    customer_id: int
    customer_name: str
    phone: Optional[str] = None
    outstanding_balance: Decimal
    communication_id: int


