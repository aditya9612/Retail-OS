from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GRNItemCreate(BaseModel):
    product_id: int
    ordered_quantity: int
    received_quantity: int
    remarks: str | None = None


class GRNCreate(BaseModel):
    purchase_order_id: int | None = None
    warehouse_id: int | None = None
    remarks: str | None = None
    items: list[GRNItemCreate]


class GRNItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    ordered_quantity: int
    received_quantity: int
    remarks: str | None


class GRNResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    purchase_order_id: int | None
    warehouse_id: int | None
    grn_number: str
    status: str
    remarks: str | None
    received_at: datetime | None
    created_at: datetime
    updated_at: datetime

    items: list[GRNItemResponse] = []
    
    
class GRNHistoryResponse(BaseModel):
    grn_id: int
    grn_number: str
    status: str
    created_at: datetime
    received_at: datetime | None
    updated_at: datetime


class GRNPrintResponse(BaseModel):
    id: int
    grn_number: str
    tenant_id: int
    purchase_order_id: int | None
    warehouse_id: int | None
    status: str
    remarks: str | None
    received_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[GRNItemResponse]