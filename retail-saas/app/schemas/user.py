from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
    store_id: Optional[int] = None
    role_id: int


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full_name cannot be empty")
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("phone cannot be empty")
        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
    store_id: Optional[int] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_update_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("full_name cannot be empty")
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_update_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("phone cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_nullable_updates(self):
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null")
        if "phone" in self.model_fields_set and self.phone is None:
            raise ValueError("phone cannot be null")
        if "password" in self.model_fields_set and self.password is None:
            raise ValueError("password cannot be null")
        return self


class RoleResponse(BaseModel):
    id: int
    name: str
    permissions: list

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: int
    tenant_id: int
    email: str
    full_name: str
    phone: Optional[str]
    store_id: Optional[int]
    role_id: int
    is_active: bool
    role: Optional[RoleResponse] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StoreBase(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    is_warehouse: bool = False


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    is_active: Optional[bool] = None
    is_warehouse: Optional[bool] = None


class StoreResponse(StoreBase):
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
