from datetime import datetime
import re
from typing import Any, Optional, Union

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.purchase_order import PurchaseOrderResponse
from app.utils.validators import validate_email_address, validate_gstin_number

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")

DISALLOWED_PLACEHOLDERS = {
    "string",
    "test",
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "unknown",
    "placeholder",
    "dummy",
    "sample",
    "000000000000000",
}

DISALLOWED_EMAIL_DOMAINS = {
    "gmli.com",
    "gmial.com",
    "gmai.com",
    "yaho.com",
    "hotmial.com",
}


def validate_name_value(value: Optional[str]) -> str:
    if value is None:
        raise ValueError("Supplier name cannot be null")
    if not isinstance(value, str):
        raise ValueError("Supplier name must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Supplier name cannot be empty or whitespace")
    if len(trimmed) < 2 or len(trimmed) > 255:
        raise ValueError("Supplier name must be between 2 and 255 characters")
    if trimmed.lower() in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Supplier name cannot be a placeholder")

    alpha_count = sum(1 for c in trimmed if c.isalpha())
    if alpha_count < 2:
        raise ValueError("Supplier name must contain at least 2 alphabetic characters")

    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .'-&,()")
    if any(c not in allowed_chars for c in trimmed):
        raise ValueError("Supplier name contains invalid characters")

    return trimmed


def validate_contact_person_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        raise ValueError("Contact person cannot be null")
    if not isinstance(value, str):
        raise ValueError("Contact person must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Contact person cannot be empty or whitespace")
    if len(trimmed) < 2 or len(trimmed) > 255:
        raise ValueError("Contact person must be between 2 and 255 characters")
    if trimmed.lower() in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Contact person cannot be a placeholder")

    if any(c.isdigit() for c in trimmed):
        raise ValueError("Contact person cannot contain digits")

    alpha_count = sum(1 for c in trimmed if c.isalpha())
    if alpha_count < 2:
        raise ValueError("Contact person must contain at least 2 alphabetic characters")

    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ .'-")
    if any(c not in allowed_chars for c in trimmed):
        raise ValueError("Contact person can contain only letters, spaces, '.', '-' and '''")

    return trimmed


def validate_address_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        raise ValueError("Address cannot be null")
    if not isinstance(value, str):
        raise ValueError("Address must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Address cannot be empty or whitespace")
    if len(trimmed) < 2 or len(trimmed) > 500:
        raise ValueError("Address must be between 2 and 500 characters")
    if trimmed.lower() in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Address cannot be a placeholder")

    alpha_count = sum(1 for c in trimmed if c.isalpha())
    if alpha_count < 2:
        raise ValueError("Address must contain at least 2 alphabetic characters")

    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.-/#()'")
    if any(c not in allowed_chars for c in trimmed):
        raise ValueError("Address contains invalid characters")

    return trimmed


def validate_email_value(value: Optional[Any]) -> Optional[Any]:
    if value is None:
        return None
    val_str = str(value).strip().lower()
    if not val_str:
        raise ValueError("Supplier email cannot be empty or whitespace")
    if val_str in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Supplier email cannot be placeholder")
    if "@" not in val_str:
        raise ValueError("Invalid email format")
    local_part, domain_part = val_str.rsplit("@", 1)
    if not local_part or not domain_part:
        raise ValueError("Invalid email format")
    if "." not in domain_part:
        raise ValueError("Email domain must contain a top-level domain")
    domain_labels = domain_part.split(".")
    tld = domain_labels[-1]
    if len(tld) < 2 or not tld.isalpha():
        raise ValueError("Invalid top-level domain in email")
    if domain_part in DISALLOWED_EMAIL_DOMAINS:
        raise ValueError(f"Disallowed email domain: {domain_part}")
    if local_part in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Email username cannot be a placeholder")
    validate_email_address(str(value), field_name="Supplier email", required=True)
    return value


def validate_phone_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Phone number must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Phone number cannot be empty or whitespace")
    if trimmed.lower() in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Phone number cannot be a placeholder")

    if trimmed.startswith("+91"):
        number = trimmed[3:]
        if len(number) != 10:
            raise ValueError(
                "Phone number with +91 must contain exactly 10 digits after +91"
            )
    else:
        number = trimmed
        if len(number) != 10:
            raise ValueError(
                "Phone number must contain exactly 10 digits"
            )

    if not number.isdigit():
        raise ValueError(
            "Phone number must contain digits only"
        )

    if number[0] not in "6789":
        raise ValueError(
            "Indian phone number must start with 6, 7, 8 or 9"
        )

    return trimmed


def validate_gstin_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid Indian GSTIN format")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("GSTIN cannot be empty or whitespace")
    if len(trimmed) != 15:
        raise ValueError("GSTIN must be exactly 15 characters")
    if trimmed != trimmed.upper():
        raise ValueError("Invalid Indian GSTIN format")
    if trimmed.lower() in DISALLOWED_PLACEHOLDERS:
        raise ValueError("Invalid Indian GSTIN format")

    if not GSTIN_REGEX.match(trimmed):
        raise ValueError("Invalid Indian GSTIN format")

    state_code = int(trimmed[:2])
    if state_code < 1 or (state_code > 38 and state_code not in (97, 99)):
        raise ValueError("Invalid Indian GSTIN state code")

    validate_gstin_number(trimmed, field_name="GSTIN", required=True)

    return trimmed


class SupplierBase(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=255,
        description="Supplier name must be between 2 and 255 characters"
    )

    contact_person: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
        description="Contact person name must be between 2 and 255 characters"
    )

    email: Optional[EmailStr] = Field(
        default=None,
        description="Enter a valid email address"
    )

    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=13,
        description="Indian phone number: 10 digits or +91 followed by 10 digits"
    )

    address: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=500,
        description="Address must be between 2 and 500 characters"
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
        description="GSTIN must be exactly 15 characters"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_name_value(value)

    @field_validator("contact_person")
    @classmethod
    def validate_contact_person(cls, value: Optional[str]) -> Optional[str]:
        return validate_contact_person_value(value)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: Optional[str]) -> Optional[str]:
        return validate_address_value(value)

    @field_validator("email")
    @classmethod
    def validate_supplier_email(cls, value: Optional[EmailStr]) -> Optional[str]:
        return validate_email_value(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_phone_value(value)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: Optional[str]) -> Optional[str]:
        return validate_gstin_value(value)


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255
    )

    contact_person: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255
    )

    email: Optional[EmailStr] = None

    phone: Optional[str] = None

    address: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=500
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15
    )

    @field_validator("name")
    @classmethod
    def validate_update_name(cls, value: Optional[str]) -> Optional[str]:
        return validate_name_value(value)

    @field_validator("contact_person")
    @classmethod
    def validate_update_contact_person(cls, value: Optional[str]) -> Optional[str]:
        return validate_contact_person_value(value)

    @field_validator("address")
    @classmethod
    def validate_update_address(cls, value: Optional[str]) -> Optional[str]:
        return validate_address_value(value)

    @field_validator("email")
    @classmethod
    def validate_update_supplier_email(cls, value: Optional[EmailStr]) -> Optional[str]:
        return validate_email_value(value)

    @field_validator("phone")
    @classmethod
    def validate_update_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_phone_value(value)

    @field_validator("gstin")
    @classmethod
    def validate_update_gstin(cls, value: Optional[str]) -> Optional[str]:
        return validate_gstin_value(value)


class SupplierResponse(BaseModel):

    id: int
    tenant_id: int
    name: str
    contact_person: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class SupplierEmptyResponse(BaseModel):

    success: bool = True
    message: str
    data: list[Any] = []


class SupplierStatsResponse(BaseModel):

    total_suppliers: int
    active_suppliers: int
    inactive_suppliers: int


class SupplierStatusUpdate(BaseModel):

    is_active: bool

    @model_validator(mode="before")
    @classmethod
    def validate_status_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("Invalid status. Expected one of: active, inactive.")

        if "is_active" in data:
            val = data["is_active"]
        elif "status" in data:
            val = data["status"]
        else:
            raise ValueError("Invalid status. Expected one of: active, inactive.")

        if isinstance(val, bool):
            return {"is_active": val}

        if isinstance(val, str):
            clean = val.strip().lower()
            if clean in ("active", "true"):
                return {"is_active": True}
            elif clean in ("inactive", "false"):
                return {"is_active": False}
            else:
                raise ValueError("Invalid status. Expected one of: active, inactive.")

        raise ValueError("Invalid status. Expected one of: active, inactive.")


class SupplierPurchaseHistoryResponse(BaseModel):
    supplier_id: int
    supplier_name: str
    total_purchases: int
    purchase_history: list[PurchaseOrderResponse]
    message: str

    model_config = {
        "from_attributes": True
    }
