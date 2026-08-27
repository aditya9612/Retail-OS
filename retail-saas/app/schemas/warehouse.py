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

    address: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Warehouse name cannot be empty")
        
        if value.lower() == "string":
           raise ValueError("Please provide a valid warehouse name")
        
        if value.isdigit():
            raise ValueError("Warehouse name cannot contain only numbers")

        if not re.search(r"[A-Za-z]", value):
            raise ValueError("Warehouse name must contain at least one alphabetic character")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError(
                "Warehouse code cannot be empty"
            )
        
        if value == "STRING":
           raise ValueError("Please provide a valid warehouse code")
        
        if value.isdigit():
            raise ValueError(
                "Warehouse code cannot contain only numbers"
            )

        if not re.fullmatch(r"[A-Z0-9_-]+", value):
            raise ValueError(
                "Warehouse code can contain only letters, numbers, '-' and '_'"
            )

        return value

    @field_validator("address")
    @classmethod
    def validate_address(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Warehouse address cannot be empty"
            )
        
        if value.lower() == "string":
            raise ValueError(
               "Please provide a valid warehouse address"
            )
        
        return value


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

    address: str = Field(
        default=None,
        min_length=2,
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
            raise ValueError(
                "Store ID cannot be null"
            )

        return value

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            raise ValueError(
                "Warehouse name cannot be null"
            )

        value = value.strip()

        if not value:
            raise ValueError(
                "Warehouse name cannot be empty"
            )
        
        if value.lower() == "string":
            raise ValueError(
               "Please provide a valid warehouse name"
            )
        
        if value.isdigit():
            raise ValueError(
                "Warehouse name cannot contain only numbers"
            )

        if not re.search(r"[A-Za-z]", value):
            raise ValueError(
                "Warehouse name must contain at least one alphabetic character"
            )

        return value

    @field_validator("code")
    @classmethod
    def validate_code(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            raise ValueError(
                "Warehouse code cannot be null"
            )

        value = value.strip().upper()

        if not value:
            raise ValueError(
                "Warehouse code cannot be empty"
            )
        
        if value == "STRING":
            raise ValueError(
               "Please provide a valid warehouse code"
            )
        
        if value.isdigit():
            raise ValueError(
                "Warehouse code cannot contain only numbers"
            )

        if not re.fullmatch(r"[A-Z0-9_-]+", value):
            raise ValueError(
                "Warehouse code can contain only letters, numbers, '-' and '_'"
            )

        return value

    @field_validator("address")
    @classmethod
    def validate_address(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            raise ValueError(
                "Warehouse address cannot be null"
            )

        value = value.strip()

        if not value:
            raise ValueError(
                "Warehouse address cannot be empty"
            )
        
        if value.lower() == "string":
            raise ValueError(
               "Please provide a valid warehouse address"
            )
        
        return value

    @field_validator("is_active")
    @classmethod
    def validate_is_active(
        cls,
        value: bool | None,
    ) -> bool | None:

        if value is None:
            raise ValueError(
                "is_active cannot be null"
            )

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