from pydantic import BaseModel, ConfigDict


class StoreCreate(BaseModel):
    name: str
    code: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None
    gstin: str | None = None
    is_warehouse: bool = False


class StoreUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None
    gstin: str | None = None
    is_active: bool | None = None
    is_warehouse: bool | None = None


class StoreResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None
    gstin: str | None = None
    is_active: bool
    is_warehouse: bool

    model_config = ConfigDict(from_attributes=True)