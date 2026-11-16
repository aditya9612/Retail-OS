from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DISALLOWED_DAMAGE_REASON_PLACEHOLDERS = {
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
    "damage",
    "damaged",
    "reason",
    "broken",
    "fault",
    "defect",
    "default",
}


def validate_damage_reason(value: str | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Damage reason must be a string")

    v = value.strip()
    if not v:
        return None

    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_DAMAGE_REASON_PLACEHOLDERS or clean_norm in DISALLOWED_DAMAGE_REASON_PLACEHOLDERS:
        raise ValueError(f"Damage reason cannot be generic placeholder '{value}'")

    if len(v) < 3 or len(v) > 255:
        raise ValueError("Damage reason must be between 3 and 255 characters")

    if v.isdigit():
        raise ValueError("Damage reason cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Damage reason must contain at least one alphabetic character")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError("Damage reason cannot consist of repeating characters")

    return v


def validate_rejection_reason_strict(value: str | None) -> str:
    if value is None:
        raise ValueError("Rejection reason cannot be null")
    if not isinstance(value, str):
        raise ValueError("Rejection reason must be a string")
    v = value.strip()
    if not v:
        raise ValueError("Rejection reason cannot be empty or whitespace")
    clean_norm = re.sub(r"[^a-zA-Z0-9]", "", v.lower())
    if v.lower() in DISALLOWED_DAMAGE_REASON_PLACEHOLDERS or clean_norm in DISALLOWED_DAMAGE_REASON_PLACEHOLDERS:
        raise ValueError(f"Rejection reason cannot be generic placeholder '{value}'")
    if len(v) < 3 or len(v) > 1000:
        raise ValueError("Rejection reason must be between 3 and 1000 characters")
    if v.isdigit():
        raise ValueError("Rejection reason cannot contain only numbers")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Rejection reason must contain at least one alphabetic character")
    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError("Rejection reason cannot consist of repeating characters")
    return v


FORBIDDEN_VEHICLE_NUMBER_PLACEHOLDERS = {
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
    "vehicle",
    "truck",
    "tempo",
    "default",
    "auto",
    "car",
    "lorry",
    "trailer",
    "transport",
}


def validate_grn_vehicle_number(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    if not isinstance(v, str):
        raise ValueError("Vehicle number must be a string")

    cleaned = v.strip()
    if not cleaned:
        return None

    lower = cleaned.lower()
    if lower in FORBIDDEN_VEHICLE_NUMBER_PLACEHOLDERS:
        raise ValueError(f"Vehicle number cannot be generic placeholder '{cleaned}'")

    norm = re.sub(r"[-_\s/.]", "", lower)
    if norm in FORBIDDEN_VEHICLE_NUMBER_PLACEHOLDERS:
        raise ValueError(f"Vehicle number cannot be generic placeholder '{cleaned}'")

    if len(cleaned) < 4 or len(cleaned) > 30:
        raise ValueError("Vehicle number must be between 4 and 30 characters")

    has_alpha = bool(re.search(r"[A-Za-z]", cleaned))
    has_digit = bool(re.search(r"[0-9]", cleaned))
    if not (has_alpha and has_digit):
        raise ValueError("Vehicle number must be a valid registration number containing letters and digits (e.g., MH-12-AB-1234)")

    if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9\-\s\.]*$", cleaned) or any(char in cleaned for char in "@#$%^*_=+"):
        raise ValueError("Vehicle number contains invalid special characters")

    alnum_only = re.sub(r"[^A-Za-z0-9]", "", cleaned)
    if alnum_only and len(set(alnum_only.lower())) <= 2 and len(alnum_only) > 4:
        raise ValueError("Vehicle number cannot be repeating dummy characters")

    return cleaned.upper()


DISALLOWED_TRANSPORTER_PLACEHOLDERS = {
    "string",
    "test",
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "unknown",
    "dummy",
    "placeholder",
    "sample",
    "transporter",
    "transport",
    "default",
}


def validate_grn_transporter_name(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("Transporter name must be a string")
    cleaned = v.strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if lower in DISALLOWED_TRANSPORTER_PLACEHOLDERS:
        raise ValueError(f"Transporter name cannot be generic placeholder '{cleaned}'")
    norm = re.sub(r"[-_\s/.]", "", lower)
    if norm in DISALLOWED_TRANSPORTER_PLACEHOLDERS:
        raise ValueError(f"Transporter name cannot be generic placeholder '{cleaned}'")
    if len(cleaned) < 2 or len(cleaned) > 100:
        raise ValueError("Transporter name must be between 2 and 100 characters")
    if not re.search(r"[A-Za-z]", cleaned):
        raise ValueError("Transporter name must contain letters")
    alpha_chars = [c.lower() for c in cleaned if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError("Transporter name cannot consist of repeating characters")
    return cleaned


FORBIDDEN_GRN_BATCH_PLACEHOLDERS = {
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
    "batch",
    "default",
}


def validate_grn_batch_number(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None

    if not isinstance(v, str):
        raise ValueError("Batch number must be a string")

    cleaned = v.strip()
    if not cleaned:
        return None

    lower = cleaned.lower()
    if lower in FORBIDDEN_GRN_BATCH_PLACEHOLDERS:
        raise ValueError(f"Batch number contains an invalid placeholder value: '{cleaned}'")

    norm = re.sub(r"[-_\s/.]", "", lower)
    if norm in FORBIDDEN_GRN_BATCH_PLACEHOLDERS or (
        norm and norm in {"na", "none", "null", "undefined", "dummy", "test", "string", "abc", "batch"}
    ):
        raise ValueError(f"Batch number contains an invalid placeholder value: '{cleaned}'")

    if len(cleaned) < 2 or len(cleaned) > 100:
        raise ValueError("Batch number must be between 2 and 100 characters")

    if not re.search(r"[a-zA-Z0-9]", cleaned):
        raise ValueError("Batch number must contain alphanumeric characters")

    if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9\-_/.]*$", cleaned) or "@" in cleaned or "*" in cleaned:
        raise ValueError("Batch number contains invalid special characters")

    alnum_only = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
    if alnum_only and len(set(alnum_only.lower())) == 1 and len(alnum_only) > 1:
        raise ValueError("Batch number cannot be repeated dummy characters")

    if alnum_only in {"123", "1234", "12345", "123456", "1234567", "12345678", "987654321", "012345"}:
        raise ValueError("Batch number cannot be a sequential dummy value")

    return cleaned


DISALLOWED_REMARKS_PLACEHOLDERS = {
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
    "remarks",
}


def validate_grn_remarks(value: str | None) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("Remarks must be a string")

    v = value.strip()
    if not v:
        raise ValueError("Remarks cannot be empty")

    if v.lower() in DISALLOWED_REMARKS_PLACEHOLDERS:
        raise ValueError("Please provide a valid remarks")

    if len(v) < 3 or len(v) > 1000:
        raise ValueError("Remarks must be between 3 and 1000 characters")

    if v.isdigit():
        raise ValueError("Remarks cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Remarks must contain at least one alphabetic character")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError("Remarks cannot consist of repeating characters")

    return v



def validate_grn_expiry_date(v: Optional[date]) -> Optional[date]:
    if v is None:
        return None
    if v <= date.today():
        raise ValueError("Product expiry date cannot be equal to or earlier than the receiving date (must be in the future)")
    return v


class GRNItemCreate(BaseModel):
    product_id: int = Field(gt=0, description="Product ID must be positive")
    ordered_quantity: Optional[int] = Field(default=None, gt=0, description="Ordered quantity must be greater than 0")
    received_quantity: int = Field(default=1, ge=0, description="Received quantity")
    accepted_quantity: Optional[int] = Field(default=None, ge=0, description="Accepted quantity")
    rejected_quantity: Optional[int] = Field(default=0, ge=0, description="Rejected quantity")
    damage_reason: Optional[str] = Field(default=None, max_length=255)
    unit_cost: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"))
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    remarks: Optional[str] = Field(default=None, max_length=500)

    @field_validator("batch_number")
    @classmethod
    def validate_item_batch_number(cls, v: Optional[str]) -> Optional[str]:
        return validate_grn_batch_number(v)

    @field_validator("damage_reason")
    @classmethod
    def validate_item_damage_reason(cls, v: str | None) -> str | None:
        return validate_damage_reason(v)

    @field_validator("remarks")
    @classmethod
    def validate_item_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)

    @field_validator("expiry_date")
    @classmethod
    def validate_item_expiry_date(cls, v: Optional[date]) -> Optional[date]:
        return validate_grn_expiry_date(v)


    @model_validator(mode="after")
    def validate_received_vs_ordered(self) -> "GRNItemCreate":
        if self.ordered_quantity is not None and self.ordered_quantity > 0 and self.received_quantity > self.ordered_quantity:
            raise ValueError(
                f"Received quantity ({self.received_quantity}) cannot be greater than ordered quantity ({self.ordered_quantity})"
            )
        return self


class GRNCreate(BaseModel):
    purchase_order_id: Optional[int] = Field(default=None, gt=0, description="Purchase order ID")
    warehouse_id: Optional[int] = Field(default=None, gt=0, description="Warehouse ID")
    store_id: Optional[int] = Field(default=None, gt=0, description="Store ID")
    invoice_number: Optional[str] = Field(default=None, max_length=100)
    invoice_date: Optional[date] = None
    vehicle_number: Optional[str] = Field(default=None, max_length=50)
    transporter_name: Optional[str] = Field(default=None, max_length=100)
    remarks: Optional[str] = Field(default=None, max_length=1000)
    items: list[GRNItemCreate] = Field(default_factory=list)

    @field_validator("invoice_number")
    @classmethod
    def validate_root_invoice_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if cleaned.lower() in {"string", "test", "null", "none", "undefined", "n/a", "na", "unknown", "placeholder", "dummy", "sample"}:
            raise ValueError(f"Invoice number cannot be generic placeholder '{cleaned}'")
        if len(cleaned) < 2 or len(cleaned) > 100:
            raise ValueError("Invoice number must be between 2 and 100 characters")
        return cleaned

    @field_validator("vehicle_number")
    @classmethod
    def validate_root_vehicle_number(cls, v: Optional[str]) -> Optional[str]:
        return validate_grn_vehicle_number(v)

    @field_validator("transporter_name")
    @classmethod
    def validate_root_transporter_name(cls, v: Optional[str]) -> Optional[str]:
        return validate_grn_transporter_name(v)

    @field_validator("remarks")
    @classmethod
    def validate_root_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)

    @model_validator(mode="after")
    def validate_items_present(self) -> "GRNCreate":
        if not self.purchase_order_id and not self.items:
            raise ValueError("At least one item is required")
        return self


class GRNItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    ordered_quantity: int
    received_quantity: int
    accepted_quantity: Optional[int] = None
    rejected_quantity: Optional[int] = 0
    reason: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = None
    remarks: Optional[str] = None

    @property
    def damage_reason(self) -> Optional[str]:
        return self.reason

    @model_validator(mode="before")
    @classmethod
    def sync_item_reason_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "reason" not in data or data.get("reason") is None:
                data["reason"] = data.get("damage_reason")
        return data


class GRNResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    purchase_order_id: Optional[int] = None
    purchase_order_number: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    grn_number: str
    status: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    remarks: Optional[str] = None
    reason: Optional[str] = None
    received_at: Optional[datetime] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    received_by_id: Optional[int] = None
    received_by_name: Optional[str] = None

    # Aggregated metrics
    total_items_count: int = 0
    total_ordered_quantity: int = 0
    total_received_quantity: int = 0
    total_accepted_quantity: int = 0
    total_rejected_quantity: int = 0
    total_cost_value: Decimal = Decimal("0.00")

    created_at: datetime
    updated_at: datetime

    items: list[GRNItemResponse] = []

    @property
    def rejection_reason(self) -> Optional[str]:
        return self.reason

    @model_validator(mode="before")
    @classmethod
    def sync_reason_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "reason" not in data or data.get("reason") is None:
                data["reason"] = data.get("rejection_reason")
        return data


class GRNItemQCUpdate(BaseModel):
    item_id: int = Field(gt=0, description="GRN item ID")
    accepted_quantity: int = Field(ge=0, description="Quantity accepted into stock")
    rejected_quantity: int = Field(default=0, ge=0, description="Quantity rejected / damaged")
    damage_reason: Optional[str] = Field(default=None, max_length=255)
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None
    remarks: Optional[str] = Field(default=None, max_length=500)

    @field_validator("batch_number")
    @classmethod
    def validate_qc_batch_number(cls, v: Optional[str]) -> Optional[str]:
        return validate_grn_batch_number(v)

    @field_validator("damage_reason")
    @classmethod
    def validate_qc_damage_reason(cls, v: str | None) -> str | None:
        return validate_damage_reason(v)

    @field_validator("remarks")
    @classmethod
    def validate_qc_item_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)

    @field_validator("expiry_date")
    @classmethod
    def validate_qc_expiry_date(cls, v: Optional[date]) -> Optional[date]:
        return validate_grn_expiry_date(v)


    @model_validator(mode="after")
    def validate_qc_rejection_and_damage(self) -> "GRNItemQCUpdate":
        if self.accepted_quantity == 0 and self.rejected_quantity == 0:
            raise ValueError(
                "Received quantity cannot be left without acceptance or rejection. Both accepted_quantity and rejected_quantity cannot be 0."
            )
        if self.rejected_quantity > 0 and (not self.damage_reason or not self.damage_reason.strip()):
            raise ValueError("Damage reason is required when rejected quantity is greater than 0")
        return self


class GRNQualityCheckRequest(BaseModel):
    items: list[GRNItemQCUpdate] = Field(..., min_length=1)
    remarks: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("remarks")
    @classmethod
    def validate_qc_remarks(cls, v: str | None) -> str | None:
        return validate_grn_remarks(v)


class GRNRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        title="Rejection Reason",
        description="Reason for GRN rejection",
    )

    @field_validator("reason")
    @classmethod
    def validate_reject_reason(cls, v: str | None) -> str:
        return validate_rejection_reason_strict(v)


class GRNHistoryEvent(BaseModel):
    event: str
    timestamp: datetime
    performed_by: Optional[str] = None
    details: Optional[str] = None


class GRNHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grn_id: int
    grn_number: str
    status: str
    created_at: datetime
    received_at: Optional[datetime] = None
    updated_at: datetime
    created_by_name: Optional[str] = None
    received_by_name: Optional[str] = None
    rejection_reason: Optional[str] = None
    timeline: list[GRNHistoryEvent] = []


class GRNStatsResponse(BaseModel):
    total_grns: int
    pending_grns: int
    received_grns: int
    rejected_grns: int
    received_today: int
    total_inward_value: Decimal
    recent_grns: list[GRNResponse] = []


class GRNPrintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grn_number: str
    tenant_id: int
    purchase_order_id: Optional[int] = None
    purchase_order_number: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    status: str
    remarks: Optional[str] = None
    reason: Optional[str] = None
    received_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    received_by_name: Optional[str] = None

    total_items_count: int = 0
    total_ordered_quantity: int = 0
    total_received_quantity: int = 0
    total_accepted_quantity: int = 0
    total_rejected_quantity: int = 0
    total_cost_value: Decimal = Decimal("0.00")

    created_at: datetime
    updated_at: datetime
    items: list[GRNItemResponse] = []


class GRNDeleteResponse(BaseModel):
    success: bool = True
    message: str
    id: int

