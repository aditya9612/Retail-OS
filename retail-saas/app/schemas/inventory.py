import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


FORBIDDEN_PLACEHOLDERS = {
    "string",
    "test",
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "abc",
    "----",
    "...",
    "???",
    "!@#$",
    "@#$%",
}


def _validate_semantic_text(v: Optional[str], field_name: str, min_len: int = 1) -> Optional[str]:
    if v is None:
        return None
    cleaned = v.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty or whitespace")
    if cleaned.lower() in FORBIDDEN_PLACEHOLDERS:
        raise ValueError(f"{field_name} contains an invalid placeholder value")
    if re.fullmatch(r"^[^\w\s]+$", cleaned):
        raise ValueError(f"{field_name} cannot consist only of punctuation or special characters")
    if len(cleaned) < min_len:
        raise ValueError(f"{field_name} is too short")
    return cleaned


class InventoryResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    product_id: int
    quantity: int
    min_stock_level: int = 0
    max_stock_level: int = 0
    reorder_point: int = 0
    low_stock_threshold: int = 10
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LowStockResponse(BaseModel):
    success: bool
    message: str
    count: int
    data: list[InventoryResponse]


class InventoryEmptyResponse(BaseModel):
    success: bool = True
    message: str = "No inventory found"
    data: list[InventoryResponse] = Field(default_factory=list)


class ExpiryEmptyResponse(BaseModel):
    success: bool = True
    message: str = "No expired inventory found"
    data: list[InventoryResponse] = Field(default_factory=list)


class InventoryValuationResponse(BaseModel):
    total_inventory_value: Decimal


FORBIDDEN_BATCH_PLACEHOLDERS = {
    "string",
    "test",
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "abc",
    "----",
    "---",
    "--",
    "...",
    "???",
    "!@#$",
    "@#$%",
    "dummy",
    "placeholder",
    "sample",
    "temp",
}


class StockInRequest(BaseModel):
    store_id: int = Field(gt=0, description="Store ID must be positive")
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, le=100000, description="Quantity must be between 1 and 100000")
    supplier_id: Optional[int] = Field(default=None, gt=0)
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = Field(default=None, ge=Decimal("1.00"), le=Decimal("999999.99"), description="Unit cost must be at least 1.00")
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("batch_number")
    @classmethod
    def validate_batch_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("batch_number cannot be null")
        if not isinstance(v, str):
            raise ValueError("batch_number must be a string")
        if v != v.strip():
            raise ValueError("batch_number cannot have leading or trailing whitespace")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("batch_number cannot be empty or whitespace")
        if len(cleaned) < 3:
            raise ValueError("batch_number must be at least 3 characters")

        lower = cleaned.lower()
        if lower in FORBIDDEN_BATCH_PLACEHOLDERS:
            raise ValueError("batch_number contains an invalid placeholder value")

        norm = re.sub(r"[-_\s/.]", "", lower)
        if norm in FORBIDDEN_BATCH_PLACEHOLDERS or (norm and norm in {"na", "none", "null", "undefined", "dummy", "test", "string", "abc"}):
            raise ValueError("batch_number contains an invalid placeholder value")

        if not re.search(r"[a-zA-Z0-9]", cleaned):
            raise ValueError("batch_number must contain alphanumeric characters")

        if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9\-_/. ]*$", cleaned) or "@" in cleaned or "*" in cleaned:
            raise ValueError("batch_number contains invalid special characters")

        alnum_only = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
        if alnum_only and len(set(alnum_only.lower())) == 1 and len(alnum_only) > 1:
            raise ValueError("batch_number cannot be repeated dummy characters")

        if alnum_only in {"123", "1234", "12345", "123456", "1234567", "12345678", "987654321", "012345"}:
            raise ValueError("batch_number cannot be a sequential dummy value")

        return cleaned

    @field_validator("expiry_date", mode="before")
    @classmethod
    def validate_expiry_date_raw(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("expiry_date cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("expiry_date cannot be empty or whitespace")
        return v

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v < date.today():
            raise ValueError("Expiry date cannot be in the past")
        return v

    @field_validator("unit_cost", mode="before")
    @classmethod
    def validate_unit_cost_raw(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("unit_cost must be a numeric value, not boolean")
        if v is None:
            raise ValueError("unit_cost cannot be null")
        if isinstance(v, str) and not v.strip():
            raise ValueError("unit_cost cannot be empty or whitespace")
        return v

    @field_validator("unit_cost")
    @classmethod
    def validate_unit_cost(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < Decimal("1.00"):
            raise ValueError("unit_cost must be at least 1.00")
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("notes cannot be empty or whitespace")
        if cleaned.isdigit():
            raise ValueError("notes cannot be purely numeric, please provide meaningful text")
        if len(cleaned) < 3:
            raise ValueError("notes must be at least 3 characters")
        if len(re.findall(r"[a-zA-Z]", cleaned)) < 3:
            raise ValueError("notes must contain at least 3 alphabetic letters")
        if "@" in cleaned or "*" in cleaned:
            raise ValueError("notes contains invalid characters")
        alnum = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
        if alnum and len(set(alnum.lower())) == 1 and len(alnum) > 1:
            raise ValueError("notes cannot consist of repeated characters")
        return _validate_semantic_text(cleaned, "notes", min_len=3)


class StockOutRequest(BaseModel):
    store_id: int = Field(gt=0, description="Store ID must be positive")
    product_id: int = Field(gt=0, description="Product ID must be positive")
    quantity: int = Field(gt=0, le=100000, description="Quantity must be between 1 and 100000")
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("notes cannot be empty or whitespace")
        if cleaned.isdigit():
            raise ValueError("notes cannot be purely numeric, please provide meaningful text")
        if len(cleaned) < 3:
            raise ValueError("notes must be at least 3 characters")
        if len(re.findall(r"[a-zA-Z]", cleaned)) < 3:
            raise ValueError("notes must contain at least 3 alphabetic letters")
        if "@" in cleaned or "*" in cleaned:
            raise ValueError("notes contains invalid characters")
        alnum = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
        if alnum and len(set(alnum.lower())) == 1 and len(alnum) > 1:
            raise ValueError("notes cannot consist of repeated characters")
        return _validate_semantic_text(cleaned, "notes", min_len=3)


class StockTransferRequest(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be positive")
    from_store_id: int = Field(gt=0, description="From Store ID must be positive")
    to_store_id: int = Field(gt=0, description="To Store ID must be positive")
    quantity: int = Field(gt=0, le=100000, description="Quantity must be between 1 and 100000")
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("to_store_id")
    @classmethod
    def validate_different_stores(cls, v: int, info: ValidationInfo) -> int:
        if "from_store_id" in info.data and v == info.data["from_store_id"]:
            raise ValueError("from_store_id and to_store_id must be different")
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("notes cannot be empty or whitespace")
        if cleaned.isdigit():
            raise ValueError("notes cannot be purely numeric, please provide meaningful text")
        if len(cleaned) < 3:
            raise ValueError("notes must be at least 3 characters")
        if len(re.findall(r"[a-zA-Z]", cleaned)) < 3:
            raise ValueError("notes must contain at least 3 alphabetic letters")
        if "@" in cleaned or "*" in cleaned:
            raise ValueError("notes contains invalid characters")
        alnum = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
        if alnum and len(set(alnum.lower())) == 1 and len(alnum) > 1:
            raise ValueError("notes cannot consist of repeated characters")
        return _validate_semantic_text(cleaned, "notes", min_len=3)


class StockMovementResponse(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    product_id: int
    movement_type: str
    quantity: int
    previous_stock: int = 0
    new_stock: int = 0
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def resolve_reference_fields(self) -> "StockMovementResponse":
        if self.reference_type and any(self.reference_type.startswith(p) for p in ("IN-", "OUT-", "TR-", "ADJ-")):
            if not self.reference or self.reference == self.reference_type:
                self.reference = self.reference_type
            self.reference_type = self.movement_type
        return self
 
 
class StockInResponse(StockMovementResponse):
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = None


class StockMovementEmptyResponse(BaseModel):
    success: bool = True
    message: str = "No inventory movements found"
    data: list[StockMovementResponse] = Field(default_factory=list)


class InventoryAdjustmentRequest(BaseModel):
    store_id: int = Field(
        gt=0,
        description="Store ID must be positive"
    )
    product_id: int = Field(
        gt=0,
        description="Product ID must be positive"
    )
    quantity: int = Field(
        gt=0,
        le=100000,
        description="Quantity must be between 1 and 100000"
    )
    adjustment_type: str = Field(
        pattern="^(increase|decrease)$"
    )
    reason: str = Field(
        min_length=3,
        max_length=500,
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if v is None:
            raise ValueError("reason cannot be null")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("reason cannot be empty or whitespace")
        if cleaned.isdigit():
            raise ValueError("reason cannot be purely numeric, please provide meaningful text")
        if len(cleaned) < 3:
            raise ValueError("reason must be at least 3 characters")
        if len(re.findall(r"[a-zA-Z]", cleaned)) < 3:
            raise ValueError("reason must contain at least 3 alphabetic letters")
        if "@" in cleaned or "*" in cleaned:
            raise ValueError("reason contains invalid characters")
        alnum = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
        if alnum and len(set(alnum.lower())) == 1 and len(alnum) > 1:
            raise ValueError("reason cannot consist of repeated characters")
        return _validate_semantic_text(cleaned, "reason", min_len=3)


class InventoryDashboardResponse(BaseModel):
    total_products: int
    total_stock: int
    total_stock_value: Decimal
    low_stock_items: int
    expired_products: int
    pending_transfers: int
    pending_purchase_orders: int

