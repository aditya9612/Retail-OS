from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.validators import (
    MAJOR_INDIAN_CITIES_STATE_MAP,
    validate_carrier_credentials,
    validate_city_name,
    validate_code,
    validate_email_format,
    validate_indian_phone,
    validate_indian_state,
    validate_meaningful_text,
    validate_person_name,
    validate_pincodes_list,
    validate_positive_int,
    validate_positive_money,
    validate_real_address,
    validate_single_pincode,
    validate_strict_bool,
    validate_tracking_number,
    validate_tracking_url,
    validate_zone_pincodes_match_state,
)


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class DeliveryStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        description="Delivery status: pending, assigned, out_for_delivery, delivered, cancelled",
    )

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: Any) -> str:
        if value is None:
            raise ValueError("Status cannot be null")

        if not isinstance(value, str):
            raise ValueError("Status must be a string")

        v = value.strip().lower()

        if not v:
            raise ValueError("Status cannot be empty or whitespace")

        allowed = {s.value for s in DeliveryStatus}
        if v not in allowed:
            raise ValueError(
                f"Invalid status: '{value}'. Allowed statuses are: {', '.join(sorted(allowed))}"
            )

        return v


class DeliveryResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    status: str
    delivery_person: Optional[str] = None
    tracking_number: Optional[str] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    partner_id: Optional[int] = None
    partner_name: Optional[str] = None
    partner_code: Optional[str] = None
    delivery_method_id: Optional[int] = None
    method_name: Optional[str] = None
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None

    is_cod: bool = False
    cod_amount: Decimal = Decimal("0.00")
    cod_collected: bool = False
    cod_collected_at: Optional[datetime] = None

    dispatched_at: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    delivery_slot: Optional[str] = None

    attempt_count: int = 0
    failure_reason: Optional[str] = None

    delivery_otp: Optional[str] = None
    pod_image_url: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    delivery_address: Optional[str] = None
    tracking_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("is_cod", "cod_collected", mode="before")
    @classmethod
    def sanitize_bool(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)

    @field_validator("cod_amount", mode="before")
    @classmethod
    def sanitize_decimal(cls, v: Any) -> Decimal:
        if v is None:
            return Decimal("0.00")
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0.00")

    @field_validator("attempt_count", mode="before")
    @classmethod
    def sanitize_int(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except Exception:
            return 0


class DeliveryListResponse(BaseModel):
    success: bool = True
    message: str = "Deliveries retrieved successfully"
    data: list[DeliveryResponse] = Field(default_factory=list)
    total: int = 0
    page: Optional[int] = None
    page_size: Optional[int] = None
    total_pages: Optional[int] = None


class SingleDeliveryResponse(BaseModel):
    success: bool = True
    message: str = "Delivery retrieved successfully"
    data: DeliveryResponse


class DeliveryMessageResponse(BaseModel):
    success: bool = False
    message: str


# Legacy validator aliases that delegate directly to centralized validators
def validate_delivery_person_name(value: Any, required: bool = True) -> Optional[str]:
    return validate_person_name(value, field_name="Delivery person name", required=required)


def validate_method_name(value: Any, required: bool = True) -> Optional[str]:
    return validate_meaningful_text(value, field_name="Method name", min_length=2, max_length=100, required=required)


def validate_method_code(value: Any, required: bool = True) -> Optional[str]:
    return validate_code(value, field_name="Method code", min_length=2, max_length=50, required=required)


def validate_zone_name(value: Any, required: bool = True) -> Optional[str]:
    return validate_meaningful_text(value, field_name="Zone name", min_length=2, max_length=100, required=required)


def validate_zone_code(value: Any, required: bool = True) -> Optional[str]:
    return validate_code(value, field_name="Zone code", min_length=2, max_length=50, required=required)


def validate_partner_name(value: Any, required: bool = True) -> Optional[str]:
    return validate_meaningful_text(value, field_name="Partner name", min_length=2, max_length=100, required=required)


def validate_partner_code(value: Any, required: bool = True) -> Optional[str]:
    return validate_code(value, field_name="Partner code", min_length=2, max_length=50, required=required)


class DeliveryCreate(BaseModel):
    order_id: int = Field(..., gt=0, description="Order ID must be a positive integer")
    delivery_person: Optional[str] = Field(default=None, description="Optional delivery person name")
    tracking_number: Optional[str] = Field(default=None, description="Optional tracking number")
    partner_id: Optional[int] = Field(default=None, gt=0, description="Optional delivery partner ID")
    delivery_method_id: Optional[int] = Field(default=None, gt=0, description="Optional delivery method ID")
    zone_id: Optional[int] = Field(default=None, gt=0, description="Optional delivery zone ID")
    is_cod: Optional[bool] = Field(default=None, description="Flag indicating Cash On Delivery")
    cod_amount: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"), description="COD amount to collect")
    delivery_slot: Optional[str] = Field(default=None, max_length=50, description="Optional delivery time slot")
    estimated_delivery_time: Optional[datetime] = Field(default=None, description="Expected delivery date and time")
    dispatched_at: Optional[datetime] = Field(default=None, description="Dispatched timestamp")

    @field_validator("order_id", mode="before")
    @classmethod
    def check_order_id(cls, value: Any) -> int:
        if value is None:
            raise ValueError("Order ID cannot be null")
        if isinstance(value, bool):
            raise ValueError("Order ID cannot be a boolean")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("Order ID must be an integer, not decimal")
        try:
            val = int(value)
        except Exception:
            raise ValueError("Order ID must be a valid integer")
        if val <= 0:
            raise ValueError("Order ID must be a positive integer (> 0)")
        return val

    @field_validator("delivery_person", mode="before")
    @classmethod
    def validate_person(cls, value: Any) -> Optional[str]:
        return validate_person_name(value, field_name="Delivery person name", required=False)

    @field_validator("tracking_number", mode="before")
    @classmethod
    def validate_tracking(cls, value: Any) -> Optional[str]:
        return validate_tracking_number(value, field_name="Tracking number", required=False)


class DeliveryCancelRequest(BaseModel):
    reason: str = Field(..., description="Cancellation reason (required)")

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, value: Any) -> str:
        res = validate_meaningful_text(
            value,
            field_name="Cancellation reason",
            min_length=2,
            max_length=500,
            required=True,
        )
        if not res:
            raise ValueError("Cancellation reason cannot be empty")
        return res


class DeliveryPartnerAssignRequest(BaseModel):
    delivery_person: Optional[str] = Field(default=None, description="Delivery person name")
    partner_id: Optional[int] = Field(default=None, gt=0, description="Optional delivery partner ID")
    tracking_number: Optional[str] = Field(default=None, description="Optional tracking number")

    @field_validator("delivery_person", mode="before")
    @classmethod
    def validate_person(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        res = validate_person_name(value, field_name="Delivery person name", required=True)
        if not res:
            raise ValueError("Delivery person name cannot be null")
        return res

    @field_validator("tracking_number", mode="before")
    @classmethod
    def validate_tracking(cls, value: Any) -> Optional[str]:
        return validate_tracking_number(value, field_name="Tracking number", required=False)

    @model_validator(mode="after")
    def check_at_least_one(self):
        if not self.delivery_person and not self.partner_id:
            raise ValueError("Either delivery_person or partner_id must be provided")
        return self


class DeliveryFailedAttemptRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255, description="Failure reason")
    remarks: Optional[str] = Field(default=None, max_length=500, description="Additional notes")
    reschedule_date: Optional[datetime] = Field(default=None, description="Rescheduled date/time")

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason_field(cls, value: Any) -> str:
        res = validate_meaningful_text(value, field_name="Failure reason", min_length=3, max_length=255, required=True)
        if not res:
            raise ValueError("Failure reason cannot be empty")
        return res


class CODCollectRequest(BaseModel):
    amount: Optional[Decimal] = Field(default=None, ge=Decimal("0.00"), description="Amount collected (optional)")


class CODDeliveryItem(BaseModel):
    delivery_id: int
    order_id: int
    order_number: str
    delivery_person: Optional[str] = None
    partner_id: Optional[int] = None
    partner_name: Optional[str] = None
    cod_amount: Decimal = Decimal("0.00")
    cod_collected: bool = False
    cod_collected_at: Optional[datetime] = None
    delivery_status: str
    delivered_at: Optional[datetime] = None
    recipient_name: Optional[str] = "Retail Customer"
    recipient_phone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("cod_amount", mode="before")
    @classmethod
    def sanitize_cod_amount(cls, v: Any) -> Decimal:
        if v is None:
            return Decimal("0.00")
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0.00")

    @field_validator("cod_collected", mode="before")
    @classmethod
    def sanitize_cod_collected(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)

    @field_validator("recipient_name", mode="before")
    @classmethod
    def sanitize_recipient_name(cls, v: Any) -> str:
        if not v:
            return "Retail Customer"
        return str(v)


class CODReconciliationSummary(BaseModel):
    total_cod_orders: int = 0
    total_cod_amount: Decimal = Decimal("0.00")
    collected_orders_count: int = 0
    total_collected_amount: Decimal = Decimal("0.00")
    pending_orders_count: int = 0
    total_pending_amount: Decimal = Decimal("0.00")
    by_delivery_person: dict[str, Decimal] = Field(default_factory=dict)


class CODReconciliationResponse(BaseModel):
    success: bool = True
    message: str = "COD reconciliation data retrieved successfully"
    summary: CODReconciliationSummary
    deliveries: list[CODDeliveryItem] = Field(default_factory=list)


class ThermalLabelMode(str, Enum):
    preview = "preview"
    view = "view"
    download = "download"
    html = "html"
    json = "json"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class DeliveryThermalLabelResponse(BaseModel):
    success: bool = True
    message: str = "Thermal delivery label generated successfully"
    html: str
    delivery_id: int
    order_number: str


class DeliveryAddressUpdateRequest(BaseModel):
    delivery_address: str = Field(..., description="Destination delivery address")

    @field_validator("delivery_address", mode="before")
    @classmethod
    def validate_address(cls, value: Any) -> str:
        res = validate_real_address(value, field_name="Delivery address", min_length=3, max_length=500, required=True)
        if not res:
            raise ValueError("Delivery address cannot be empty")
        return res


class DeliveryLabelData(BaseModel):
    delivery_id: int
    order_id: int
    order_number: str
    tracking_number: Optional[str] = None
    delivery_person: Optional[str] = None
    status: str
    recipient_name: str
    recipient_phone: Optional[str] = None
    delivery_address: Optional[str] = None
    barcode: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliveryLabelResponse(BaseModel):
    success: bool = True
    message: str = "Delivery label generated successfully"
    data: DeliveryLabelData


class DeliveryTrackingData(BaseModel):
    delivery_id: int
    order_id: int
    status: str
    tracking_number: Optional[str] = None
    delivery_person: Optional[str] = None
    tracking_id: Optional[int] = None
    remarks: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DeliveryTrackingResponse(BaseModel):
    success: bool = True
    message: str = "Delivery tracking retrieved successfully"
    data: DeliveryTrackingData


class DeliveryHistoryItem(BaseModel):
    id: int
    order_id: int
    status: str
    remarks: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliveryHistoryResponse(BaseModel):
    success: bool = True
    message: str = "Delivery history retrieved successfully"
    data: list[DeliveryHistoryItem] = Field(default_factory=list)
    total: int = 0


class DeliveryStatsData(BaseModel):
    total_deliveries: int = 0
    pending_deliveries: int = 0
    assigned_deliveries: int = 0
    out_for_delivery_deliveries: int = 0
    delivered_deliveries: int = 0
    cancelled_deliveries: int = 0

    model_config = ConfigDict(from_attributes=True)


class DeliveryStatsResponse(BaseModel):
    success: bool = True
    message: str = "Delivery statistics retrieved successfully"
    data: DeliveryStatsData


class DeliveryMethodCreate(BaseModel):
    name: str = Field(..., description="Method name between 2 and 100 characters")
    code: str = Field(..., description="Unique method code (alphanumeric, underscores, hyphens)")
    description: Optional[str] = Field(default=None, description="Meaningful description (optional)")
    cost: Decimal = Field(..., gt=Decimal("0.00"), description="Delivery cost must be greater than zero")
    estimated_days: Optional[int] = Field(default=None, gt=0, le=60, description="Estimated delivery days (1-60)")
    is_active: bool = Field(default=True, description="Active status")

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value: Any) -> str:
        res = validate_meaningful_text(value, field_name="Method name", min_length=2, max_length=100, required=True)
        if not res:
            raise ValueError("Method name cannot be empty")
        return res

    @field_validator("code", mode="before")
    @classmethod
    def check_code(cls, value: Any) -> str:
        res = validate_code(value, field_name="Method code", min_length=2, max_length=50, required=True)
        if not res:
            raise ValueError("Method code cannot be empty")
        return res

    @field_validator("description", mode="before")
    @classmethod
    def check_description(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Description", min_length=2, max_length=255, required=False)

    @field_validator("cost", mode="before")
    @classmethod
    def check_cost(cls, value: Any) -> Decimal:
        if value is None:
            raise ValueError("Cost is required and must be greater than zero")
        res = validate_positive_money(value, field_name="Cost", required=True, allow_zero=False)
        if res is None or res <= Decimal("0.00"):
            raise ValueError("Cost must be greater than zero")
        return res

    @field_validator("estimated_days", mode="before")
    @classmethod
    def check_days(cls, value: Any) -> Optional[int]:
        return validate_positive_int(value, field_name="Estimated days", required=False, max_value=60)

    @field_validator("is_active", mode="before")
    @classmethod
    def check_active(cls, value: Any) -> bool:
        res = validate_strict_bool(value, field_name="is_active", required=True)
        return res if res is not None else True


class DeliveryMethodUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Method name between 2 and 100 characters")
    code: Optional[str] = Field(default=None, description="Unique method code")
    description: Optional[str] = Field(default=None, description="Optional description up to 255 characters")
    cost: Optional[Decimal] = Field(default=None, gt=Decimal("0.00"), description="Delivery cost must be greater than zero")
    estimated_days: Optional[int] = Field(default=None, gt=0, le=60, description="Estimated delivery days (1-60)")
    is_active: Optional[bool] = Field(default=None, description="Active status")

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Method name", min_length=2, max_length=100, required=False)

    @field_validator("code", mode="before")
    @classmethod
    def check_code(cls, value: Any) -> Optional[str]:
        return validate_code(value, field_name="Method code", min_length=2, max_length=50, required=False)

    @field_validator("description", mode="before")
    @classmethod
    def check_description(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Description", min_length=2, max_length=255, required=False)

    @field_validator("cost", mode="before")
    @classmethod
    def check_cost(cls, value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        res = validate_positive_money(value, field_name="Cost", required=False, allow_zero=False)
        if res is not None and res <= Decimal("0.00"):
            raise ValueError("Cost must be greater than zero")
        return res

    @field_validator("estimated_days", mode="before")
    @classmethod
    def check_days(cls, value: Any) -> Optional[int]:
        return validate_positive_int(value, field_name="Estimated days", required=False, max_value=60)

    @field_validator("is_active", mode="before")
    @classmethod
    def check_active(cls, value: Any) -> Optional[bool]:
        return validate_strict_bool(value, field_name="is_active", required=False)


class DeliveryMethodResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    description: Optional[str] = None
    cost: Decimal
    estimated_days: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SingleDeliveryMethodResponse(BaseModel):
    success: bool = True
    message: str = "Delivery method retrieved successfully"
    data: DeliveryMethodResponse


class DeliveryMethodListResponse(BaseModel):
    success: bool = True
    message: str = "Delivery methods retrieved successfully"
    data: list[DeliveryMethodResponse] = Field(default_factory=list)
    total: int = 0


class DeliveryZoneCreate(BaseModel):
    name: str = Field(..., description="Zone name between 3 and 100 characters")
    code: str = Field(..., description="Unique zone code (alphanumeric, underscores, hyphens)")
    description: Optional[str] = Field(default=None, description="Zone description (optional)")
    city: Optional[str] = Field(default=None, description="Optional city name")
    state: Optional[str] = Field(default=None, description="Optional state name")
    pincodes: list[str] = Field(default_factory=list, description="List of 6-digit postal pincodes")
    is_active: bool = Field(default=True, description="Active status")

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value: Any) -> str:
        res = validate_meaningful_text(value, field_name="Zone name", min_length=3, max_length=100, required=True)
        if not res:
            raise ValueError("Zone name cannot be empty")
        return res

    @field_validator("code", mode="before")
    @classmethod
    def check_code(cls, value: Any) -> str:
        res = validate_code(value, field_name="Zone code", min_length=2, max_length=50, required=True)
        if not res:
            raise ValueError("Zone code cannot be empty")
        return res

    @field_validator("description", mode="before")
    @classmethod
    def check_description(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Description", min_length=3, max_length=255, required=False)

    @field_validator("city", mode="before")
    @classmethod
    def check_city(cls, value: Any) -> Optional[str]:
        return validate_city_name(value, required=False)

    @field_validator("state", mode="before")
    @classmethod
    def check_state(cls, value: Any) -> Optional[str]:
        return validate_indian_state(value, required=False)

    @field_validator("pincodes", mode="before")
    @classmethod
    def check_pincodes(cls, value: Any) -> list[str]:
        return validate_pincodes_list(value, required=True)

    @field_validator("is_active", mode="before")
    @classmethod
    def check_active(cls, value: Any) -> bool:
        res = validate_strict_bool(value, field_name="is_active", required=True)
        return res if res is not None else True

    @model_validator(mode="after")
    def validate_geo_consistency(self) -> "DeliveryZoneCreate":
        if self.city and self.state:
            c_low = self.city.strip().lower()
            s_low = self.state.strip().lower()
            if c_low == s_low and s_low not in ("delhi", "chandigarh"):
                raise ValueError(f"City '{self.city}' cannot be identical to state '{self.state}'")
            if c_low in MAJOR_INDIAN_CITIES_STATE_MAP:
                exp_st = MAJOR_INDIAN_CITIES_STATE_MAP[c_low]
                if exp_st.lower() != s_low:
                    raise ValueError(f"City '{self.city}' belongs to state '{exp_st}', not '{self.state}'")

        if (self.state or self.city) and self.pincodes:
            validate_zone_pincodes_match_state(self.pincodes, state=self.state, city=self.city)

        return self


class DeliveryZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Zone name between 3 and 100 characters")
    code: Optional[str] = Field(default=None, description="Unique zone code")
    description: Optional[str] = Field(default=None, description="Optional description up to 255 characters")
    city: Optional[str] = Field(default=None, description="Optional city name")
    state: Optional[str] = Field(default=None, description="Optional state name")
    pincodes: Optional[list[str]] = Field(default=None, description="List of 6-digit postal pincodes")
    is_active: Optional[bool] = Field(default=None, description="Active status")

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Zone name", min_length=3, max_length=100, required=False)

    @field_validator("code", mode="before")
    @classmethod
    def check_code(cls, value: Any) -> Optional[str]:
        return validate_code(value, field_name="Zone code", min_length=2, max_length=50, required=False)

    @field_validator("description", mode="before")
    @classmethod
    def check_description(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Description", min_length=3, max_length=255, required=False)

    @field_validator("city", mode="before")
    @classmethod
    def check_city(cls, value: Any) -> Optional[str]:
        return validate_city_name(value, required=False)

    @field_validator("state", mode="before")
    @classmethod
    def check_state(cls, value: Any) -> Optional[str]:
        return validate_indian_state(value, required=False)

    @field_validator("pincodes", mode="before")
    @classmethod
    def check_pincodes(cls, value: Any) -> Optional[list[str]]:
        return validate_pincodes_list(value, required=False)

    @field_validator("is_active", mode="before")
    @classmethod
    def check_active(cls, value: Any) -> Optional[bool]:
        return validate_strict_bool(value, field_name="is_active", required=False)

    @model_validator(mode="after")
    def validate_geo_consistency(self) -> "DeliveryZoneUpdate":
        if self.city and self.state:
            c_low = self.city.strip().lower()
            s_low = self.state.strip().lower()
            if c_low == s_low and s_low not in ("delhi", "chandigarh"):
                raise ValueError(f"City '{self.city}' cannot be identical to state '{self.state}'")
            if c_low in MAJOR_INDIAN_CITIES_STATE_MAP:
                exp_st = MAJOR_INDIAN_CITIES_STATE_MAP[c_low]
                if exp_st.lower() != s_low:
                    raise ValueError(f"City '{self.city}' belongs to state '{exp_st}', not '{self.state}'")

        if (self.state or self.city) and self.pincodes:
            validate_zone_pincodes_match_state(self.pincodes, state=self.state, city=self.city)

        return self


class DeliveryZoneResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    description: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincodes: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SingleDeliveryZoneResponse(BaseModel):
    success: bool = True
    message: str = "Delivery zone retrieved successfully"
    data: DeliveryZoneResponse


class DeliveryZoneListResponse(BaseModel):
    success: bool = True
    message: str = "Delivery zones retrieved successfully"
    data: list[DeliveryZoneResponse] = Field(default_factory=list)
    total: int = 0


class DeliveryPartnerConnect(BaseModel):
    name: str = Field(..., description="Partner name between 2 and 100 characters")
    code: str = Field(..., description="Unique partner code (alphanumeric, underscores, hyphens)")
    description: str = Field(..., description="Meaningful description (required)")
    contact_email: Optional[str] = Field(default=None, description="Optional contact email")
    contact_phone: Optional[str] = Field(default=None, description="Optional contact phone")
    api_key: Optional[str] = Field(default=None, description="Optional API key for carrier integration")
    api_secret: Optional[str] = Field(default=None, description="Optional API secret for carrier integration")
    tracking_url_template: Optional[str] = Field(default=None, description="Optional tracking URL template")
    is_active: bool = Field(default=True, description="Active status")

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value: Any) -> str:
        res = validate_meaningful_text(value, field_name="Partner name", min_length=2, max_length=100, required=True)
        if not res:
            raise ValueError("Partner name cannot be empty")
        return res

    @field_validator("code", mode="before")
    @classmethod
    def check_code(cls, value: Any) -> str:
        res = validate_code(value, field_name="Partner code", min_length=2, max_length=50, required=True)
        if not res:
            raise ValueError("Partner code cannot be empty")
        return res

    @field_validator("description", mode="before")
    @classmethod
    def check_description(cls, value: Any) -> str:
        res = validate_meaningful_text(value, field_name="Description", min_length=2, max_length=255, required=True)
        if not res:
            raise ValueError("Description cannot be empty")
        return res

    @field_validator("contact_email", mode="before")
    @classmethod
    def check_email(cls, value: Any) -> Optional[str]:
        return validate_email_format(value, field_name="Contact email", required=False)

    @field_validator("contact_phone", mode="before")
    @classmethod
    def check_phone(cls, value: Any) -> Optional[str]:
        return validate_indian_phone(value, field_name="Contact phone", required=False)

    @field_validator("api_key", mode="before")
    @classmethod
    def check_api_key(cls, value: Any) -> Optional[str]:
        return validate_carrier_credentials(value, field_name="API key", required=False)

    @field_validator("api_secret", mode="before")
    @classmethod
    def check_api_secret(cls, value: Any) -> Optional[str]:
        return validate_carrier_credentials(value, field_name="API secret", required=False)

    @field_validator("tracking_url_template", mode="before")
    @classmethod
    def check_tracking_url(cls, value: Any) -> Optional[str]:
        return validate_tracking_url(value, field_name="Tracking URL template", required=False)

    @field_validator("is_active", mode="before")
    @classmethod
    def check_active(cls, value: Any) -> bool:
        res = validate_strict_bool(value, field_name="is_active", required=True)
        return res if res is not None else True


class DeliveryPartnerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Partner name between 2 and 100 characters")
    code: Optional[str] = Field(default=None, description="Unique partner code")
    description: Optional[str] = Field(default=None, description="Optional description up to 255 characters")
    contact_email: Optional[str] = Field(default=None, description="Optional contact email")
    contact_phone: Optional[str] = Field(default=None, description="Optional contact phone")
    api_key: Optional[str] = Field(default=None, description="Optional API key")
    api_secret: Optional[str] = Field(default=None, description="Optional API secret")
    tracking_url_template: Optional[str] = Field(default=None, description="Optional tracking URL template")
    is_active: Optional[bool] = Field(default=None, description="Active status")

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "DeliveryPartnerUpdate":
        fields = [
            self.name,
            self.code,
            self.description,
            self.contact_email,
            self.contact_phone,
            self.api_key,
            self.api_secret,
            self.tracking_url_template,
            self.is_active,
        ]
        if all(f is None for f in fields):
            raise ValueError("At least one field must be provided for update")
        return self

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Partner name", min_length=2, max_length=100, required=False)

    @field_validator("code", mode="before")
    @classmethod
    def check_code(cls, value: Any) -> Optional[str]:
        return validate_code(value, field_name="Partner code", min_length=2, max_length=50, required=False)

    @field_validator("description", mode="before")
    @classmethod
    def check_description(cls, value: Any) -> Optional[str]:
        return validate_meaningful_text(value, field_name="Description", min_length=2, max_length=255, required=False)

    @field_validator("contact_email", mode="before")
    @classmethod
    def check_email(cls, value: Any) -> Optional[str]:
        return validate_email_format(value, field_name="Contact email", required=False)

    @field_validator("contact_phone", mode="before")
    @classmethod
    def check_phone(cls, value: Any) -> Optional[str]:
        return validate_indian_phone(value, field_name="Contact phone", required=False)

    @field_validator("api_key", mode="before")
    @classmethod
    def check_api_key(cls, value: Any) -> Optional[str]:
        return validate_carrier_credentials(value, field_name="API key", required=False)

    @field_validator("api_secret", mode="before")
    @classmethod
    def check_api_secret(cls, value: Any) -> Optional[str]:
        return validate_carrier_credentials(value, field_name="API secret", required=False)

    @field_validator("tracking_url_template", mode="before")
    @classmethod
    def check_tracking_url(cls, value: Any) -> Optional[str]:
        return validate_tracking_url(value, field_name="Tracking URL template", required=False)

    @field_validator("is_active", mode="before")
    @classmethod
    def check_active(cls, value: Any) -> Optional[bool]:
        return validate_strict_bool(value, field_name="is_active", required=False)


class DeliveryPartnerResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    description: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    tracking_url_template: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SingleDeliveryPartnerResponse(BaseModel):
    success: bool = True
    message: str = "Delivery partner retrieved successfully"
    data: DeliveryPartnerResponse


class DeliveryPartnerListResponse(BaseModel):
    success: bool = True
    message: str = "Delivery partners retrieved successfully"
    data: list[DeliveryPartnerResponse] = Field(default_factory=list)
    total: int = 0


class ServiceabilityData(BaseModel):
    pincode: str
    is_serviceable: bool
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    zone_code: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class ServiceabilityResponse(BaseModel):
    success: bool = True
    message: str
    data: ServiceabilityData


class ServiceabilityUploadData(BaseModel):
    total_rows_processed: int
    pincodes_added: int
    pincodes_existing: int
    zones_updated: list[str] = Field(default_factory=list)


class ServiceabilityUploadResponse(BaseModel):
    success: bool = True
    message: str
    data: ServiceabilityUploadData