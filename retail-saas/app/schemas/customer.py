from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CustomerBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: str
    address: Optional[str] = None
    birthday: Optional[date] = None
    whatsapp_opt_in: bool = True
    sms_opt_in: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    birthday: Optional[date] = None
    whatsapp_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None


class CustomerResponse(CustomerBase):
    id: int
    tenant_id: int
    loyalty_points: int
    created_at: datetime

    model_config = {"from_attributes": True}
