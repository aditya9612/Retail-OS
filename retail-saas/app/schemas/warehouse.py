from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WarehouseCreate(BaseModel):
    store_id: int | None = None
    name: str
    code: str
    address: str | None = None


class WarehouseUpdate(BaseModel):
    store_id: int | None = None
    name: str | None = None
    code: str | None = None
    address: str | None = None
    is_active: bool | None = None


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    store_id: int | None
    name: str
    code: str
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime