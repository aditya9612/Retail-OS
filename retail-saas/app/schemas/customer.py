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
    if not any(c.isalpha() for c in v):
        raise ValueError("Name must contain at least one alphabetic character")
    if v.isdigit():
        raise ValueError("Name cannot consist only of digits")
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

    @field_validator("address")
    @classmethod
    def check_create_address(cls, v: str) -> str:
        if v is None:
            raise ValueError("Address is required")
        v = v.strip()
        if not v:
            raise ValueError("Address cannot be empty or whitespace")
        return v

    @field_validator("birthday")
    @classmethod
    def check_create_birthday(cls, v: date) -> date:
        if v is None:
            raise ValueError("Birthday is required")
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

    @field_validator("birthday")
    @classmethod
    def validate_birthday(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and value > date.today():
            raise ValueError("Birthday cannot be in the future")

        return value


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    message: str
    message: str


class CustomerStatsResponse(BaseModel):
    total_customers: int
    active_customers: int
    inactive_customers: int
    blocked_customers: int
    new_customers: int
    regular_customers: int
    vip_customers: int



class CustomerFeedbackCreate(BaseModel):
    customer_id: int = Field(gt=0)
    invoice_id: Optional[int] = Field(default=None, gt=0)
    rating: int = Field(ge=1, le=5)
    feedback: str = Field(min_length=1, max_length=2000)


    @field_validator("comments")
    @classmethod
    def validate_comments(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


    @field_validator("comments")
    @classmethod
    def validate_comments(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class CustomerFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    rating: int
    feedback: str
    created_at: datetime




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
        if not v or not v.strip():
            raise ValueError("Remarks cannot be empty or whitespace")
        return v.strip()


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
        if not v or not v.strip():
            raise ValueError("Remarks cannot be empty or whitespace")
        return v.strip()


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    balance: Decimal


class WalletTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
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



class LoyaltyEarnRequest(BaseModel):
    customer_id: int = Field(gt=0)
    points: int = Field(gt=0)
    reason: Optional[str] = Field(default=Field(default=None, gt=0), max_length=500)


class LoyaltyRedeemRequest(BaseModel):
    customer_id: int = Field(gt=0)
    points: int = Field(gt=0)


class LoyaltyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    points: int




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
        if not v or not v.strip():
            raise ValueError("Message cannot be empty or whitespace")
        return v.strip()


class CommunicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    channel: str
    message: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferralCreate(BaseModel):
    customer_id: int = Field(gt=0)
    referred_customer_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_referral(self):
        if self.referred_customer_id is not None and self.customer_id == self.referred_customer_id:
            raise ValueError("Customer cannot refer themselves")
        return self


class ReferralResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    referred_customer_id: int
    status: str
    created_at: datetime




class CustomerNoteCreate(BaseModel):
    customer_id: int = Field(gt=0)
    note: str = Field(min_length=1, max_length=500)

    @field_validator("note")
    @classmethod
    def validate_note(cls, v: str):
        if not v or not v.strip():
            raise ValueError("Note cannot be empty or whitespace")
        v = v.strip()
        # Prevent dangerous HTML/script injection
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
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Note contains invalid or dangerous HTML/script content")
        if "<" in v and ">" in v:
            raise ValueError("HTML tags are not allowed in customer notes")
        return v


class CustomerNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    note: str
    created_by: Optional[int] = None
    created_at: datetime




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
        if not v or not v.strip():
            raise ValueError("Message cannot be empty or whitespace")
        return v.strip()


class CampaignSendResponse(BaseModel):
    campaign_id: int
    sent_count: int
    failed_count: int
    message: str


class TopCustomerResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: str
    total_spend: float
    loyalty_points: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class RetentionResponse(BaseModel):
    total_customers: int
    retained_customers: int
    retention_rate: Decimal




class LifetimeValueResponse(BaseModel):
    customer_id: int
    customer_name: str
    lifetime_value: Decimal
    total_orders: int

    model_config = ConfigDict(from_attributes=True)


class LoyaltyReportResponse(BaseModel):
    total_customers: int
    total_points_earned: int
    total_points_redeemed: int
    total_points_balance: int

    model_config = ConfigDict(from_attributes=True)


class CustomerStatusUpdate(BaseModel):
    status: Literal["active", "inactive", "blocked"]