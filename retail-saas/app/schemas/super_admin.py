from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SuperAdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    phone: str | None = Field(
        default=None,
        max_length=20,
    )


class SuperAdminLogin(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )


class SuperAdminUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )
    phone: str | None = Field(
        default=None,
        max_length=20,
    )
    email: EmailStr | None = None


class SuperAdminStatusUpdate(BaseModel):
    is_active: bool


class SuperAdminChangePassword(BaseModel):
    current_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )


class SuperAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SuperAdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SuperAdminTenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantStatusUpdate(BaseModel):
    is_active: bool


class SuperAdminTenantUserResponse(BaseModel):
    id: int
    tenant_id: int
    email: EmailStr
    full_name: str
    phone: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SuperAdminDashboardResponse(BaseModel):
    total_super_admins: int
    active_super_admins: int
    inactive_super_admins: int
    total_tenants: int
    active_tenants: int
    inactive_tenants: int
    total_users: int