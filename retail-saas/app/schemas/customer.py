from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Literal

from pydantic import BaseModel,EmailStr, Field


class CustomerBase(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: str = Field(
        ...,
        pattern=r"^[6-9]\d{9}$",
        description="10 digit Indian mobile number"
    )
    address: Optional[str] = Field(None, max_length=500)
    birthday: Optional[date] = None
    whatsapp_opt_in: bool = True
    sms_opt_in: bool = True
    status: Literal["active", "inactive", "blocked"] = "active"
    segment: Literal["new", "regular", "vip", "inactive"] = "new"


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(
        None,
        pattern=r"^[6-9]\d{9}$"
    )
    address: Optional[str] = Field(None, max_length=500)
    birthday: Optional[date] = None
    whatsapp_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None


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
