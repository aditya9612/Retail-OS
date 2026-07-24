from datetime import date, datetime
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


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
