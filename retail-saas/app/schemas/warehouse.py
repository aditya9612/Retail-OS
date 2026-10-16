from datetime import datetime
from decimal import Decimal
import re
from typing import Any, Optional

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

    store_id: StrictInt | None = None

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

    address: str | None = None

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
        if value is not None and value <= 0:
            raise ValueError("Store ID must be greater than 0")
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
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Warehouse address cannot be empty"
            )
        
        if len(value) < 2 or len(value) > 500:
            raise ValueError(
                "Warehouse address must be between 2 and 500 characters"
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
    store_id: int | None = None
    store_name: str | None = None
    name: str
    code: str
    address: str | None = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WarehouseDashboardResponse(BaseModel):
    total_warehouses: int = Field(ge=0)
    active_warehouses: int = Field(ge=0)
    inactive_warehouses: int = Field(ge=0)
    total_stock_units: Decimal | int = 0
    total_stock_value: Decimal = Decimal("0.00")
    total_products_stored: int = 0


class WarehouseDeleteData(BaseModel):
    id: int


class WarehouseDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Warehouse deleted successfully"
    data: Optional[WarehouseDeleteData] = None


class WarehouseStatusUpdate(BaseModel):
    is_active: bool

    @model_validator(mode="before")
    @classmethod
    def validate_status_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise ValueError("Invalid status format")
        if "is_active" in data:
            val = data["is_active"]
        elif "status" in data:
            val = data["status"]
        else:
            raise ValueError("Field 'is_active' or 'status' is required")

        if isinstance(val, bool):
            return {"is_active": val}
        if isinstance(val, str):
            clean = val.strip().lower()
            if clean in ("active", "true"):
                return {"is_active": True}
            elif clean in ("inactive", "false"):
                return {"is_active": False}
        raise ValueError("Invalid status. Expected one of: active, inactive.")


class WarehouseStockItem(BaseModel):
    product_id: int
    product_name: str
    sku: str
    category_name: Optional[str] = None
    quantity: Decimal | int
    min_stock_level: int = 0
    unit_cost: Optional[Decimal] = None
    selling_price: Optional[Decimal] = None
    stock_value: Optional[Decimal] = None
    is_low_stock: bool = False


class WarehouseStockResponse(BaseModel):
    success: bool = True
    warehouse_id: int
    warehouse_name: str
    warehouse_code: str
    store_id: Optional[int] = None
    total_items: int
    total_quantity: Decimal | int
    total_stock_value: Decimal
    page: int
    page_size: int
    data: list[WarehouseStockItem] = Field(default_factory=list)


class WarehouseTransferItem(BaseModel):
    transfer_id: int
    transfer_number: Optional[str] = None
    transfer_type: str
    source_store_id: int
    source_store_name: Optional[str] = None
    destination_store_id: int
    destination_store_name: Optional[str] = None
    status: str
    item_count: int = 0
    created_at: datetime


class WarehouseTransfersResponse(BaseModel):
    success: bool = True
    warehouse_id: int
    warehouse_name: str
    total_transfers: int
    data: list[WarehouseTransferItem] = Field(default_factory=list)