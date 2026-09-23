from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SaaSSubscriptionCancelRequest(BaseModel):
    cancel_at_period_end: bool = Field(
        default=True,
        description="If True, cancellation takes effect at the end of the current billing cycle",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional reason for cancellation",
    )


class SaaSSubscriptionResponse(BaseModel):
    id: int
    tenant_id: int
    plan_id: int
    status: str
    billing_interval: str
    unit_price: Decimal
    currency: str
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime
    trial_end_date: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SaaSSubscriptionLifecycleRunResponse(BaseModel):
    trials_expired_to_past_due: int
    active_subscriptions_moved_to_past_due: int
    scheduled_cancellations_processed: int
    past_due_subscriptions_expired: int
    renewal_invoices_generated: int
