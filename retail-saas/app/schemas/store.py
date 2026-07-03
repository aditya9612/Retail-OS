import re

from pydantic import BaseModel, ConfigDict, field_validator


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()

        if len(value) < 3:
            raise ValueError("Store name must contain at least 3 characters")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z0-9_-]+", value):
            raise ValueError(
                "Store code may contain only letters, numbers, '_' and '-'"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None:
            return value

        value = value.strip()

        if not re.fullmatch(r"\d{10}", value):
            raise ValueError("Phone number must be exactly 10 digits")

        return value

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value):
        if value is None:
            return value

        value = value.strip()

        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("Pincode must be exactly 6 digits")

        return value

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value):
        if value is None:
            return value

        value = value.strip().upper()

        if not re.fullmatch(
            r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]",
            value,
        ):
            raise ValueError("Invalid GSTIN format")

        return value


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if value is None:
            return value

        value = value.strip()

        if len(value) < 3:
            raise ValueError("Store name must contain at least 3 characters")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        if value is None:
            return value

        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z0-9_-]+", value):
            raise ValueError(
                "Store code may contain only letters, numbers, '_' and '-'"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None:
            return value

        value = value.strip()

        if not re.fullmatch(r"\d{10}", value):
            raise ValueError("Phone number must be exactly 10 digits")

        return value

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value):
        if value is None:
            return value

        value = value.strip()

        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("Pincode must be exactly 6 digits")

        return value

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value):
        if value is None:
            return value

        value = value.strip().upper()

        if not re.fullmatch(
            r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]",
            value,
        ):
            raise ValueError("Invalid GSTIN format")

        return value


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