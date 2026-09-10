from datetime import date, datetime
import re
from typing import Optional, Literal
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict


def validate_phone_number(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Phone number must be a string")
    v = v.strip()
    if not v:
        raise ValueError("Phone number cannot be empty or whitespace")
    if not re.fullmatch(r"^[6-9]\d{9}$", v):
        raise ValueError("Phone number must be exactly 10 digits starting with 6, 7, 8, or 9")
    return v


def validate_customer_name(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("Name must be a string")
    v = v.strip()
    if len(v) < 2 or len(v) > 255:
        raise ValueError("Name must be between 2 and 255 characters")
    alpha_count = sum(1 for c in v if c.isalpha())
    if alpha_count < 2:
        raise ValueError("Name must contain at least two alphabetic characters")
    for c in v:
        if not (c.isalpha() or c in " '-."):
            raise ValueError("Name contains invalid characters. Only letters, spaces, apostrophes, hyphens, and periods are allowed")
    return v


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
            raise ValueError(f"{field_name} cannot be empty or whitespace")
        return None
    if len(v) < min_length or len(v) > max_length:
        raise ValueError(f"{field_name} must be between {min_length} and {max_length} characters")

    if v.lower() == "string":
        raise ValueError(f"{field_name} cannot be placeholder 'string'")

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
            raise ValueError(f"{field_name} contains invalid or dangerous HTML/script content")

    if "<" in v and ">" in v:
        raise ValueError(f"HTML tags are not allowed in {field_name.lower()}")

    alpha_count = sum(1 for c in v if c.isalpha())
    if alpha_count == 0:
        if v.isdigit():
            raise ValueError(f"{field_name} cannot be numeric-only")
        raise ValueError(f"{field_name} must contain meaningful text with letters, not only numbers or symbols")

    return v


def validate_address(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        raise ValueError("Address cannot be empty or whitespace")
    return v


def validate_birthday(v: Optional[date]) -> Optional[date]:
    if v is None:
        return None
    if v > date.today():
        raise ValueError("Birthday cannot be in the future")
    return v


class SubResourceNoDataResponse(BaseModel):
    success: bool = True
    message: str
    data: list = Field(default_factory=list)


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
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    birthday: Optional[date] = None
    whatsapp_opt_in: bool = True
    sms_opt_in: bool = True
    status: Literal["active", "inactive", "blocked"] = "active"
    segment: Literal["new", "regular", "vip", "inactive"] = "new"

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()

        if not re.fullmatch(r"^(?:\+91)?[6-9][0-9]{9}$", v):
            raise ValueError(
                "Phone number must be 10 digits starting with 6-9, "
                "or +91 followed by 10 digits starting with 6-9"
            )

        return v

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return validate_customer_name(v)

    @field_validator("address")
    @classmethod
    def check_address(cls, v: Optional[str]) -> Optional[str]:
        return validate_address(v)

    @field_validator("birthday")
    @classmethod
    def check_birthday(cls, v: Optional[date]) -> Optional[date]:
        return validate_birthday(v)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        v = v.strip().upper()
        if not v:
            raise ValueError("GSTIN cannot be empty or whitespace")

        pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
        if not re.fullmatch(pattern, v):
            raise ValueError("Invalid GSTIN format")

        return v



class CustomerCreate(CustomerBase):
    address: str = Field(..., max_length=500, description="Address is required")
    birthday: date = Field(..., description="Birthday is required")

    @field_validator("address", mode="before")
    @classmethod
    def check_create_address_before(cls, v):
        if v is None:
            raise ValueError("Address is required and cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Address cannot be empty or whitespace")
        return v

    @field_validator("address")
    @classmethod
    def check_create_address(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Address cannot be empty or whitespace")
        return v

    @field_validator("birthday", mode="before")
    @classmethod
    def check_create_birthday_before(cls, v):
        if v is None:
            raise ValueError("Birthday is required and cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Birthday cannot be empty")
        return v

    @field_validator("birthday")
    @classmethod
    def check_create_birthday(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Birthday cannot be in the future")
        return v


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, description="Phone must be exactly 10 digits")
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    birthday: Optional[date] = None
    whatsapp_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def check_update_name_before(cls, v):
        if v is None:
            raise ValueError("Name cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Name cannot be empty or whitespace")
        return v

    @field_validator("name")
    @classmethod
    def check_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_customer_name(v)

    @field_validator("phone", mode="before")
    @classmethod
    def check_update_phone_before(cls, v):
        if v is None:
            raise ValueError("Phone cannot be null")
        return v

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_phone_number(v)

    @field_validator("address", mode="before")
    @classmethod
    def check_update_address_before(cls, v):
        if v is None:
            raise ValueError("Address cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Address cannot be empty or whitespace")
        return v

    @field_validator("address")
    @classmethod
    def check_address(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_address(v)

    @field_validator("birthday", mode="before")
    @classmethod
    def check_update_birthday_before(cls, v):
        if v is None:
            raise ValueError("Birthday cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Birthday cannot be empty")
        return v

    @field_validator("birthday")
    @classmethod
    def check_birthday(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return None
        return validate_birthday(v)

    @field_validator("email", mode="before")
    @classmethod
    def check_update_email_before(cls, v):
        if v is None:
            raise ValueError("Email cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Email cannot be empty or whitespace")
        return v

    @field_validator("gstin", mode="before")
    @classmethod
    def check_update_gstin_before(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            raise ValueError("GSTIN cannot be empty or whitespace")
        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        v = v.strip().upper()
        if not v:
            raise ValueError("GSTIN cannot be empty or whitespace")

        pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
        if not re.fullmatch(pattern, v):
            raise ValueError("Invalid GSTIN format")

        return v


class CustomerResponse(CustomerBase):
    id: int
    tenant_id: int
    loyalty_points: Optional[int] = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def sanitize_status(cls, v):
        if v is None or not str(v).strip():
            return "active"
        s = str(v).strip().lower()
        return s if s in ("active", "inactive", "blocked") else "active"

    @field_validator("segment", mode="before")
    @classmethod
    def sanitize_segment(cls, v):
        if v is None or not str(v).strip():
            return "new"
        s = str(v).strip().lower()
        return s if s in ("new", "regular", "vip", "inactive") else "new"

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
    total_revenue: Optional[int] = 0
    new_this_month: Optional[int] = 0
    vip_customers: Optional[int] = 0
    inactive_customers: Optional[int] = 0
    blocked_customers: Optional[int] = 0
    new_customers: Optional[int] = 0
    regular_customers: Optional[int] = 0


class CustomerFeedbackCreate(BaseModel):
    customer_id: int = Field(gt=0)
    invoice_id: Optional[int] = Field(default=None, gt=0)
    rating: int = Field(ge=1, le=5)
    comments: Optional[str] = Field(default=None, max_length=2000)
    suggestions: Optional[str] = Field(default=None, max_length=2000)
    feedback: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("comments")
    @classmethod
    def validate_comments(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_meaningful_text(v, "Comments", 1, 2000, required=False)
        return v

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_meaningful_text(v, "Suggestions", 1, 2000, required=False)
        return v

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_meaningful_text(v, "Feedback", 1, 2000, required=False)
        return v

    @model_validator(mode="after")
    def sync_comments_and_feedback(self):
        if self.feedback and not self.comments:
            self.comments = self.feedback
        elif self.comments and not self.feedback:
            self.feedback = self.comments
        return self


class CustomerFeedbackResponse(BaseModel):
    id: int
    customer_id: int
    invoice_id: Optional[int] = None
    rating: int
    comments: Optional[str] = None
    suggestions: Optional[str] = None
    feedback: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_response_feedback(self):
        if not self.feedback and self.comments:
            self.feedback = self.comments
        return self


class WalletCreditRequest(BaseModel):
    customer_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    reference_no: str = Field(min_length=1, max_length=100)
    remarks: str = Field(min_length=1, max_length=255)

    @field_validator("reference_no")
    @classmethod
    def validate_reference(cls, v: str):
        if not v or not v.strip():
            raise ValueError("Reference number cannot be empty or whitespace")
        v = v.strip()
        if not re.fullmatch(r"^\d+$", v):
            raise ValueError("Reference number must contain numeric digits only")
        return v

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, v: str):
        return validate_meaningful_text(v, "Remarks", 1, 255, required=True)


class WalletDebitRequest(BaseModel):
    customer_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0)
    reference_no: str = Field(min_length=1, max_length=100)
    remarks: str = Field(min_length=1, max_length=255)

    @field_validator("reference_no")
    @classmethod
    def validate_reference(cls, v: str):
        if not v or not v.strip():
            raise ValueError("Reference number cannot be empty or whitespace")
        v = v.strip()
        if not re.fullmatch(r"^\d+$", v):
            raise ValueError("Reference number must contain numeric digits only")
        return v

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, v: str):
        return validate_meaningful_text(v, "Remarks", 1, 255, required=True)


class WalletResponse(BaseModel):
    id: Optional[int] = None
    customer_id: int
    current_balance: Optional[float] = None
    balance: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_balance(self):
        if self.balance is None and self.current_balance is not None:
            self.balance = Decimal(str(self.current_balance))
        elif self.current_balance is None and self.balance is not None:
            self.current_balance = float(self.balance)
        return self


class WalletTransactionResponse(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class WalletOperationResponse(BaseModel):
    id: int
    customer_id: int
    amount: float
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    balance: float
    current_balance: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class LoyaltyEarnRequest(BaseModel):
    customer_id: int = Field(gt=0)
    points: int = Field(gt=0)
    invoice_id: Optional[int] = Field(default=None, gt=0)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str):
        return validate_meaningful_text(v, "Reason", 1, 500, required=True)


class LoyaltyRedeemRequest(BaseModel):
    customer_id: int = Field(gt=0)
    points: int = Field(gt=0)


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

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_points(self):
        if self.points is None and self.balance_points is not None:
            self.points = self.balance_points
        elif self.balance_points is None and self.points is not None:
            self.balance_points = self.points
        return self


class CommunicationCreate(BaseModel):
    customer_id: int = Field(gt=0)
    communication_type: Literal["SMS", "WHATSAPP", "EMAIL"]
    message: str = Field(min_length=1, max_length=500)

    @field_validator("communication_type", mode="before")
    @classmethod
    def normalize_comm_type(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str):
        return validate_meaningful_text(v, "Message", 1, 500, required=True)


class CommunicationResponse(BaseModel):
    id: int
    customer_id: int
    communication_type: str
    message: str
    delivery_status: str
    sent_at: datetime
    channel: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_channel_and_status(self):
        if not self.channel and self.communication_type:
            self.channel = self.communication_type
        if not self.status and self.delivery_status:
            self.status = self.delivery_status
        return self


class ReferralCreate(BaseModel):
    customer_id: int = Field(gt=0)
    referred_customer_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_referral(self):
        if self.referred_customer_id is not None and self.customer_id == self.referred_customer_id:
            raise ValueError("Customer cannot refer themselves")
        return self


class ReferralResponse(BaseModel):
    id: int
    customer_id: int
    referral_code: str
    referred_customer_id: Optional[int] = None
    reward_amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerNoteCreate(BaseModel):
    customer_id: int = Field(gt=0)
    note: str = Field(min_length=1, max_length=500)

    @field_validator("note")
    @classmethod
    def validate_note(cls, v: str):
        return validate_meaningful_text(v, "Note", 1, 500, required=True)


class CustomerNoteResponse(BaseModel):
    id: int
    customer_id: int
    note: str
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CampaignSendRequest(BaseModel):
    customer_ids: list[int] = Field(min_length=1)
    communication_type: str
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("customer_ids")
    @classmethod
    def validate_customer_ids(cls, v: list[int]):
        if not v:
            raise ValueError("customer_ids cannot be empty")
        for cid in v:
            if cid <= 0:
                raise ValueError("Customer IDs must be positive integers")
        return v

    @field_validator("communication_type", mode="before")
    @classmethod
    def validate_comm_type(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
        if v not in ("SMS", "WHATSAPP", "EMAIL"):
            raise ValueError("Invalid communication type. Allowed values: SMS, WHATSAPP, EMAIL")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str):
        return validate_meaningful_text(v, "Message", 1, 1000, required=True)


class CampaignSendResponse(BaseModel):
    message: str
    total_customers: Optional[int] = None
    campaign_id: Optional[int] = None
    sent_count: Optional[int] = None
    failed_count: Optional[int] = None


class TopCustomerResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: str
    total_spend: float
    loyalty_points: int
    status: str
    order_count: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class CustomerStatusUpdate(BaseModel):
    status: Literal["active", "inactive", "blocked"]