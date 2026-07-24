from datetime import date, datetime
from typing import Optional, Literal
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict


class CustomerBase(BaseModel):
    name: str = Field(min_length=2, max_length=255, description="Name must be 2 to 255 characters")
    email: Optional[EmailStr] = None
    phone: str = Field(min_length=10, max_length=15, description="Phone must be 10 to 15 digits")
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
        if not v.isdigit():
            raise ValueError("Phone must contain digits only")
        if len(v) < 10 or len(v) > 15:
            raise ValueError("Phone must be between 10 and 15 digits")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty or whitespace")
        return v.strip()

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) != 15:
            raise ValueError("GSTIN must be exactly 15 characters")
        return v.upper() if v else v


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    birthday: Optional[date] = None
    whatsapp_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("Phone must contain digits only")
        return v


class CustomerResponse(CustomerBase):
    id: int
    tenant_id: int
    loyalty_points: int
    created_at: datetime
    status: str
    segment: str


    model_config = {"from_attributes": True}

class MessageResponse(BaseModel):
    message: str    


class CustomerStatsResponse(BaseModel):
    total_customers: int
    active_customers: int
    total_revenue: int
    new_this_month: int
    vip_customers: int

class CustomerFeedbackCreate(BaseModel):
    customer_id: int
    invoice_id: Optional[int] = None
    rating: int = Field(ge=1, le=5)
    comments: Optional[str] = Field(default=None, max_length=500)
    suggestions: Optional[str] = Field(default=None, max_length=500)

class CustomerFeedbackResponse(BaseModel):
    id: int
    customer_id: int
    invoice_id: Optional[int] = None
    rating: int
    comments: Optional[str] = None
    suggestions: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class WalletCreditRequest(BaseModel):
    customer_id: int
    amount: Decimal = Field(gt=0)
    reference_no: str = Field(max_length=100)
    remarks: Optional[str] = Field(default=None, max_length=255)

    @field_validator("reference_no")
    @classmethod
    def validate_reference(cls, v: str):
        if not v.strip():
            raise ValueError("Reference number cannot be empty")
        return v.strip()

class WalletDebitRequest(BaseModel):
    customer_id: int
    amount: Decimal = Field(gt=0)
    reference_no: str = Field(max_length=100)
    remarks: Optional[str] = Field(default=None, max_length=255)

    @field_validator("reference_no")
    @classmethod
    def validate_reference(cls, v: str):
        if not v.strip():
            raise ValueError("Reference number cannot be empty")
        return v.strip()


class WalletResponse(BaseModel):
    id: int
    customer_id: int
    current_balance: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WalletTransactionResponse(BaseModel):
    id: int
    wallet_id: int
    transaction_type: str
    amount: float
    reference_no: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class LoyaltyEarnRequest(BaseModel):
    customer_id: int
    points: int = Field(gt=0)
    invoice_id: Optional[int] = None


class LoyaltyRedeemRequest(BaseModel):
    customer_id: int
    points: int = Field(gt=0)


class LoyaltyResponse(BaseModel):
    id: int
    customer_id: int
    invoice_id: Optional[int] = None

    points_earned: int
    points_redeemed: int
    balance_points: int

    expiry_date: Optional[date] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class CommunicationCreate(BaseModel):
    customer_id: int
    communication_type: Literal["SMS", "WHATSAPP", "EMAIL"]
    message: str = Field(min_length=5, max_length=500)

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v


class CommunicationResponse(BaseModel):
    id: int
    customer_id: int
    communication_type: str
    message: str
    delivery_status: str
    sent_at: datetime

    class Config:
        from_attributes = True 

class ReferralCreate(BaseModel):
    customer_id: int
    referred_customer_id: Optional[int] = None

class ReferralResponse(BaseModel):
    id: int
    customer_id: int
    referral_code: str
    referred_customer_id: Optional[int] = None
    reward_amount: float

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class CustomerNoteCreate(BaseModel):
    customer_id: int
    note: str = Field(min_length=3, max_length=500)

    @field_validator("note")
    @classmethod
    def validate_note(cls, v):
        if not v.strip():
            raise ValueError("Note cannot be empty")
        return v

class CustomerNoteResponse(BaseModel):
    id: int
    customer_id: int
    note: str
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CampaignSendRequest(BaseModel):
    customer_ids: list[int]
    communication_type: str   
    message: str

class CampaignSendResponse(BaseModel):
    message: str
    total_customers: int

from pydantic import BaseModel

class TopCustomerResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    total_spend: float
    loyalty_points: int
    status: str

    class Config:
        from_attributes = True

class RetentionResponse(BaseModel):
    total_customers: int
    active_customers: int
    inactive_customers: int
    retention_rate: float

class LifetimeValueResponse(BaseModel):
    customer_id: int
    customer_name: str
    total_spend: float
    loyalty_points: int

    class Config:
        from_attributes = True

class LoyaltyReportResponse(BaseModel):
    customer_id: int
    customer_name: str
    points_earned: int
    points_redeemed: int
    balance_points: int

    class Config:
        from_attributes = True                                   
