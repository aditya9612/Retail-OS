from datetime import datetime
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)


DISALLOWED_WAREHOUSE_PLACEHOLDERS = {
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
    "address",
}


def validate_warehouse_name(value: str | None, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValueError("Warehouse name cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError("Warehouse name must be a string")

    v = value.strip()
    if not v:
        raise ValueError("Warehouse name cannot be empty")

    if v.lower() in DISALLOWED_WAREHOUSE_PLACEHOLDERS:
        raise ValueError("Please provide a valid warehouse name")

    if len(v) < 2 or len(v) > 100:
        raise ValueError("Warehouse name must be between 2 and 100 characters")

    if v.isdigit():
        raise ValueError("Warehouse name cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Warehouse name must contain at least one alphabetic character")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError("Warehouse name cannot consist of repeating characters")

    return v


def validate_warehouse_code(value: str | None, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise ValueError("Warehouse code cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError("Warehouse code must be a string")

    v = value.strip().upper()
    if not v:
        raise ValueError("Warehouse code cannot be empty")

    if v in ("STRING", "TEST", "NULL", "NONE", "UNDEFINED", "DUMMY", "00000"):
        raise ValueError("Please provide a valid warehouse code")

    if len(v) < 2 or len(v) > 50:
        raise ValueError("Warehouse code must be between 2 and 50 characters")

    if v.isdigit():
        raise ValueError("Warehouse code cannot contain only numbers")

    if not re.fullmatch(r"[A-Z0-9_-]+", v):
        raise ValueError("Warehouse code can contain only letters, numbers, '-' and '_'")

    alnum_chars = [c for c in v if c.isalnum()]
    if len(set(alnum_chars)) < 2:
        raise ValueError("Warehouse code cannot consist of repeating characters")

    return v


def validate_warehouse_address(value: str | None, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError("Warehouse address cannot be null")
        return None

    if not isinstance(value, str):
        raise ValueError("Warehouse address must be a string")

    v = value.strip()
    if not v:
        raise ValueError("Warehouse address cannot be empty")

    if v.lower() in DISALLOWED_WAREHOUSE_PLACEHOLDERS:
        raise ValueError("Please provide a valid warehouse address")

    if len(v) < 5 or len(v) > 500:
        raise ValueError("Warehouse address must be between 5 and 500 characters")

    if v.isdigit():
        raise ValueError("Warehouse address cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Warehouse address must contain at least one letter")

    alnum_chars = [c.lower() for c in v if c.isalnum()]
    if len(set(alnum_chars)) < 2:
        raise ValueError("Warehouse address cannot consist of repeating characters")

    if not re.fullmatch(r"[A-Za-z0-9\s,./#&'()\-]+", v):
        raise ValueError("Warehouse address contains invalid characters")

    return v


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    store_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    name: str = Field(
        min_length=2,
        max_length=100,
    )

    code: str = Field(
        min_length=2,
        max_length=50,
    )

    address: str | None = Field(
        default=None,
        min_length=5,
        max_length=500,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_warehouse_name(value, required=True)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return validate_warehouse_code(value, required=True)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        return validate_warehouse_address(value, required=False)


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    store_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
    )

    address: str | None = Field(
        default=None,
        min_length=5,
        max_length=500,
    )

    is_active: StrictBool | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError(
                "At least one field must be provided for update"
            )

        return self

    @field_validator("store_id")
    @classmethod
    def validate_store_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            raise ValueError("Store ID cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return validate_warehouse_name(value, required=True)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return validate_warehouse_code(value, required=True)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        return validate_warehouse_address(value, required=True)

    @field_validator("is_active")
    @classmethod
    def validate_is_active(
        cls,
        value: bool | None,
    ) -> bool | None:
        if value is None:
            raise ValueError("is_active cannot be null")
        return value


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    store_id: int | None
    name: str
    code: str
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

class WarehouseDashboardResponse(BaseModel):
    total_warehouses: int = Field(ge=0)
    active_warehouses: int = Field(ge=0)
    inactive_warehouses: int = Field(ge=0)


class WarehouseDeleteResponse(BaseModel):
    message: str