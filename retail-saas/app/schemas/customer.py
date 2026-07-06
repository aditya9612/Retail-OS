from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class CustomerBase(BaseModel):
    name: str = Field(min_length=2, max_length=255, description="Name must be 2 to 255 characters")
    email: Optional[EmailStr] = None
    phone: str = Field(min_length=10, max_length=15, description="Phone must be 10 to 15 digits")
    address: Optional[str] = Field(default=None, max_length=500)
    birthday: Optional[date] = None
    whatsapp_opt_in: bool = True
    sms_opt_in: bool = True

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if not v.isdigit():
            raise ValueError("Phone must contain digits only")
        if len(v) < 10 or len(v) > 15:
            raise ValueError("Phone must be between 10 and 15 digits")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be empty or whitespace")
        return v.strip()


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    address: Optional[str] = Field(default=None, max_length=500)
    birthday: Optional[date] = None
    whatsapp_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None and not v.isdigit():
            raise ValueError("Phone must contain digits only")
        return v


class CustomerResponse(CustomerBase):
    id: int
    tenant_id: int
    loyalty_points: int
    created_at: datetime

    model_config = {"from_attributes": True}