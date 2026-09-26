from datetime import datetime
from typing import Optional
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.saas_plan_entitlement import EntitlementDimension


class SaaSPlanEntitlementCreate(BaseModel):
    dimension: str = Field(..., description="Entitlement dimension name")
    value: Optional[int] = Field(None, ge=0, description="Numeric quota limit (ignored if is_unlimited=True)")
    is_unlimited: bool = Field(default=False, description="Whether this dimension has no numeric ceiling")

    @field_validator("dimension")
    @classmethod
    def validate_dimension(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in EntitlementDimension.ALL:
            raise ValueError(
                f"Invalid dimension '{v}'. Allowed dimensions: {sorted(list(EntitlementDimension.ALL))}"
            )
        return v

    @model_validator(mode="after")
    def validate_unlimited_and_value(self) -> "SaaSPlanEntitlementCreate":
        if self.is_unlimited:
            self.value = None
        else:
            if self.value is None:
                raise ValueError("Limited entitlement (is_unlimited=False) requires a numeric value >= 0")
            if self.value < 0:
                raise ValueError("Entitlement value cannot be negative")
        return self


class SaaSPlanEntitlementUpdate(BaseModel):
    value: Optional[int] = Field(None, ge=0, description="Numeric quota limit (ignored if is_unlimited=True)")
    is_unlimited: bool = Field(default=False, description="Whether this dimension has no numeric ceiling")

    @model_validator(mode="after")
    def validate_unlimited_and_value(self) -> "SaaSPlanEntitlementUpdate":
        if self.is_unlimited:
            self.value = None
        else:
            if self.value is None:
                raise ValueError("Limited entitlement (is_unlimited=False) requires a numeric value >= 0")
            if self.value < 0:
                raise ValueError("Entitlement value cannot be negative")
        return self


class SaaSPlanEntitlementResponse(BaseModel):
    id: int
    plan_id: int
    dimension: str
    value: Optional[int] = None
    is_unlimited: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SaaSPlanEntitlementListResponse(BaseModel):
    plan_id: int
    items: list[SaaSPlanEntitlementResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


class DimensionUsageResponse(BaseModel):
    dimension: str
    current_usage: int
    limit: Optional[int] = None
    is_unlimited: bool

    model_config = ConfigDict(from_attributes=True)


class SaaSUsageResponse(BaseModel):
    tenant_id: int
    plan_id: int
    plan_name: str
    plan_code: str
    subscription_status: str
    items: list[DimensionUsageResponse]
    dimensions: dict[str, DimensionUsageResponse]

    model_config = ConfigDict(from_attributes=True)
