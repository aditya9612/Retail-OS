from pydantic import BaseModel,ConfigDict
from datetime import datetime,date
from typing import Optional
from decimal import Decimal

class PaymentVerify(BaseModel):
    transaction_id: str
    status: str
    gateway_response: Optional[str] = None

class PaymentGatewayCreate(BaseModel):
    gateway_name: str
    merchant_id: str
    api_key: str
    secret_key: str
    webhook_secret: Optional[str] = None
    environment: str = "TEST"
    status: str = "ACTIVE"

class PaymentGatewayUpdate(BaseModel):
    gateway_name: Optional[str] = None
    merchant_id: Optional[str] = None
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    webhook_secret: Optional[str] = None
    environment: Optional[str] = None
    status: Optional[str] = None


class PaymentGatewayResponse(BaseModel):
    id: int
    tenant_id: int
    gateway_name: str
    merchant_id: str
    api_key: str
    secret_key: str
    webhook_secret: Optional[str] = None
    environment: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }  
class PaymentSplitCreate(BaseModel):
    transaction_id: int
    payment_method: str
    amount: Decimal


class PaymentSplitResponse(PaymentSplitCreate):
    id: int

    class Config:
        from_attributes = True  

class SettlementCreate(BaseModel):
    gateway_id: int
    settlement_date: date
    total_amount: Decimal
    status: str = "pending"
    reference_no: str | None = None


class SettlementResponse(BaseModel):
    id: int
    tenant_id: int
    gateway_id: int
    settlement_date: date
    total_amount: Decimal
    status: str
    reference_no: str | None = None

    model_config = ConfigDict(from_attributes=True)   

class PaymentWebhookLogCreate(BaseModel):
    event_type: str
    transaction_id: str
    payload: str
    status: str = "received"


class PaymentWebhookLogResponse(BaseModel):
    id: int
    tenant_id: int
    event_type: str
    transaction_id: str
    payload: str
    status: str

    model_config = ConfigDict(from_attributes=True)         

             
