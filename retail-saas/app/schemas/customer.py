from datetime import date, datetime
import re
from typing import Optional, Literal
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict


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
    def validate_name(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("Name cannot be empty or whitespace")

        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        v = v.strip().upper()

        pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"

        if not re.fullmatch(pattern, v):
            raise ValueError("Invalid GSTIN format")

        return v


class CustomerCreate(CustomerBase):
    birthday: date = Field(
        description="Customer birthday is required and cannot be in the future"
    )

    @field_validator("birthday")
    @classmethod
    def validate_birthday(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Birthday cannot be in the future")

        return value


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=13,
        description="Phone must be 10 digits or +91 followed by 10 digits",
    )
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    birthday: Optional[date] = None
    whatsapp_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        v = v.strip()

        if not re.fullmatch(r"^(?:\+91)?[6-9][0-9]{9}$", v):
            raise ValueError(
                "Phone number must be 10 digits starting with 6-9, "
                "or +91 followed by 10 digits starting with 6-9"
            )

        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        v = v.strip()

        if not v:
            raise ValueError("Name cannot be empty or whitespace")

        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        v = v.strip().upper()

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


class CustomerStatsResponse(BaseModel):
    total_customers: int
    active_customers: int
    inactive_customers: int
    blocked_customers: int
    new_customers: int
    regular_customers: int
    vip_customers: int


class CustomerFeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: str = Field(min_length=1, max_length=2000)


class CustomerFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    rating: int
    feedback: str
    created_at: datetime


class WalletCreditRequest(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    reason: Optional[str] = Field(default=None, max_length=500)


class WalletDebitRequest(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=12)
    reason: Optional[str] = Field(default=None, max_length=500)


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


class LoyaltyEarnRequest(BaseModel):
    points: int = Field(gt=0)
    reason: Optional[str] = Field(default=None, max_length=500)


class LoyaltyRedeemRequest(BaseModel):
    points: int = Field(gt=0)


class LoyaltyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    points: int


class CommunicationCreate(BaseModel):
    channel: Literal["whatsapp", "sms", "email"]
    message: str = Field(min_length=1, max_length=5000)


class CommunicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    channel: str
    message: str
    status: str
    created_at: datetime


class ReferralCreate(BaseModel):
    referred_customer_id: int = Field(gt=0)


class ReferralResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    referred_customer_id: int
    status: str
    created_at: datetime


class CustomerNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


class CustomerNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    note: str
    created_at: datetime


class CampaignSendRequest(BaseModel):
    campaign_id: int = Field(gt=0)
    channel: Literal["whatsapp", "sms", "email"]


class CampaignSendResponse(BaseModel):
    campaign_id: int
    sent_count: int
    failed_count: int
    message: str


class TopCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_name: str
    total_spend: Decimal
    order_count: int


class RetentionResponse(BaseModel):
    total_customers: int
    retained_customers: int
    retention_rate: Decimal


class LifetimeValueResponse(BaseModel):
    customer_id: int
    customer_name: str
    lifetime_value: Decimal
    total_orders: int


class LoyaltyReportResponse(BaseModel):
    total_customers: int
    total_points_earned: int
    total_points_redeemed: int
    total_points_balance: int


class CustomerStatusUpdate(BaseModel):
    status: Literal["active", "inactive", "blocked"]