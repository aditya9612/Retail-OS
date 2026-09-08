import re
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class StoreCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=20)
    address: str = Field(..., min_length=3, max_length=255)
    city: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=50)
    pincode: str = Field(..., min_length=6, max_length=6)
    phone: str = Field(..., min_length=10, max_length=10)
    gstin: Optional[str] = Field(default=None, max_length=15)
    is_warehouse: bool = False

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean_phone = v.strip()
        if len(clean_phone) != 10 or not clean_phone.isdigit():
            raise ValueError("Mobile number must be exactly 10 digits")
        if clean_phone[0] in ["0", "1", "2", "3", "4", "5"]:
            raise ValueError(f"Mobile number cannot start with '{clean_phone[0]}'. Must start with 6, 7, 8, or 9")
        if not re.fullmatch(r"^[6-9]\d{9}$", clean_phone):
            raise ValueError("Invalid Indian mobile number format")
        return clean_phone

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: str) -> str:
        clean_pin = v.strip()
        if not re.fullmatch(r"^[1-9][0-9]{5}$", clean_pin):
            raise ValueError("Pincode must be exactly 6 digits")
        return clean_pin

    @field_validator("city", "state")
    @classmethod
    def validate_text(cls, v: str, info) -> str:
        clean_val = v.strip()
        if not re.fullmatch(r"^[a-zA-Z\s]+$", clean_val):
            raise ValueError(f"{info.field_name.capitalize()} must contain only letters")
        return clean_val

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean_code = v.strip().upper()
        if not re.fullmatch(r"^[A-Z0-9_-]+$", clean_code):
            raise ValueError("Store code must contain only letters and numbers")
        return clean_code

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        clean_gst = v.strip().upper()
        if not re.fullmatch(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", clean_gst):
            raise ValueError("Invalid GSTIN format")
        return clean_gst


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


class StoreResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    address: str
    city: str
    state: str
    pincode: str
    phone: str
    gstin: Optional[str] = None
    is_active: bool = True
    is_warehouse: bool = False

    model_config = ConfigDict(
        from_attributes=True
    )