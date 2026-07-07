from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserBase(BaseModel):
    email: EmailStr = Field(description="Must be a valid email address")
    full_name: str = Field(min_length=2, max_length=255, description="Full name must be 2 to 255 characters")
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    store_id: Optional[int] = Field(default=None, gt=0)
    role_id: int = Field(gt=0, description="Role ID must be positive")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("Phone must contain digits only")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty or whitespace")
        return v.strip()


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=100, description="Password must be at least 6 characters")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    store_id: Optional[int] = Field(default=None, gt=0)
    role_id: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)

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
        if not value.isdigit():
            raise ValueError("Phone must contain digits only")
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
    permissions: list[str]

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
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=1, max_length=20)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, min_length=6, max_length=6, description="Pincode must be exactly 6 digits")
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15, description="GSTIN must be exactly 15 characters")
    is_warehouse: bool = False

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("Pincode must contain digits only")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("Phone must contain digits only")
        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) != 15:
            raise ValueError("GSTIN must be exactly 15 characters")
        return v.upper() if v else v


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, min_length=6, max_length=6)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    is_active: Optional[bool] = None
    is_warehouse: Optional[bool] = None


class StoreResponse(StoreBase):
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
