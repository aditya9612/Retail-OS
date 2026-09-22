import re
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class StoreCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=50)
    state: Optional[str] = Field(default=None, max_length=50)
    pincode: Optional[str] = Field(default=None, max_length=10)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = None
    is_main: bool = False
    gstin: Optional[str] = Field(default=None, max_length=15)
    is_warehouse: Optional[bool] = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean_name = v.strip()
        if not clean_name:
            raise ValueError("Store name cannot be empty")
        return clean_name

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        clean_phone = v.strip()
        if not re.fullmatch(r"^[0-9+ -]{7,15}$", clean_phone):
            raise ValueError("Invalid phone number format")
        return clean_phone

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        clean_pin = v.strip()
        return clean_pin

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        return v.strip()

    @field_validator("city", "state")
    @classmethod
    def validate_text(cls, v: Optional[str], info) -> Optional[str]:
        if not v or not v.strip():
            return None
        return v.strip()

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        clean_code = v.strip().upper()
        return clean_code

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        clean_gst = v.strip().upper()
        if not re.fullmatch(
            r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
            clean_gst,
        ):
            raise ValueError("Invalid GSTIN format")
        return clean_gst


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_main: Optional[bool] = None
    gstin: Optional[str] = None
    is_active: Optional[bool] = None
    is_warehouse: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_update_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_name(v)

    @field_validator("address")
    @classmethod
    def validate_update_address(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_address(v)

    @field_validator("phone")
    @classmethod
    def validate_update_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_phone(v)

    @field_validator("pincode")
    @classmethod
    def validate_update_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_pincode(v)

    @field_validator("city")
    @classmethod
    def validate_update_city(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_city(v)

    @field_validator("state")
    @classmethod
    def validate_update_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_state(v)

    @field_validator("gstin")
    @classmethod
    def validate_update_gstin(
        cls, v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return None

        return StoreCreate.validate_gstin(v)


class StoreResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_main: bool = False
    gstin: Optional[str] = None
    is_active: bool = True
    is_warehouse: bool = False

    model_config = ConfigDict(
        from_attributes=True
    )