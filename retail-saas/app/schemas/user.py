from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserBase(BaseModel):
    email: EmailStr = Field(description="Valid email address is required")
    full_name: str = Field(min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    store_id: Optional[int] = Field(default=None, gt=0)
    role_id: int = Field(gt=0)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        value = str(value).strip().lower()
        if not value:
            raise ValueError("Email cannot be empty")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be empty")
        if not any(char.isalpha() for char in value):
            raise ValueError("Full name must contain alphabetic characters")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Phone cannot be empty")

        if not value.isdigit():
            raise ValueError("Phone must contain digits only")

        if len(value) < 10 or len(value) > 15:
            raise ValueError("Phone must contain 10 to 15 digits")

        return value


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password cannot be empty")

        if len(value) < 6:
            raise ValueError("Password must be at least 6 characters")

        if not any(char.isupper() for char in value):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in value):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one number")

        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    store_id: Optional[int] = Field(default=None, gt=0)
    role_id: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError("Full name cannot be empty")

        if not any(char.isalpha() for char in value):
            raise ValueError("Full name must contain alphabetic characters")

        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = str(value).strip()

        if not value:
            raise ValueError("Phone cannot be empty")

        if not value.isdigit():
            raise ValueError("Phone must contain digits only")

        if len(value) < 10 or len(value) > 15:
            raise ValueError("Phone must contain 10 to 15 digits")

        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        if not value.strip():
            raise ValueError("Password cannot be empty")

        if len(value) < 6:
            raise ValueError("Password must be at least 6 characters")

        if not any(char.isupper() for char in value):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in value):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one number")

        return value

    @model_validator(mode="after")
    def validate_updates(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update")

        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("Full name cannot be null")

        if "phone" in self.model_fields_set and self.phone is None:
            raise ValueError("Phone cannot be null")

        if "password" in self.model_fields_set and self.password is None:
            raise ValueError("Password cannot be null")

        if "store_id" in self.model_fields_set and self.store_id is not None:
            if self.store_id <= 0:
                raise ValueError("Store ID must be greater than 0")

        if "role_id" in self.model_fields_set and self.role_id is not None:
            if self.role_id <= 0:
                raise ValueError("Role ID must be greater than 0")

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
    pincode: Optional[str] = Field(default=None, min_length=6, max_length=6)
    phone: Optional[str] = Field(default=None, min_length=10, max_length=15)
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    is_warehouse: bool = False

    @field_validator("name", "code", "address", "city", "state")
    @classmethod
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        if not value.isdigit():
            raise ValueError("Pincode must contain digits only")

        if len(value) != 6:
            raise ValueError("Pincode must contain exactly 6 digits")

        return value

    @field_validator("phone")
    @classmethod
    def validate_store_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        if not value.isdigit():
            raise ValueError("Phone must contain digits only")

        if len(value) < 10 or len(value) > 15:
            raise ValueError("Phone must contain 10 to 15 digits")

        return value

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        value = value.strip().upper()

        if len(value) != 15:
            raise ValueError("GSTIN must contain exactly 15 characters")

        if not value.isalnum():
            raise ValueError("GSTIN must contain only letters and digits")

        return value


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

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update")

        return self


class StoreResponse(StoreBase):
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}