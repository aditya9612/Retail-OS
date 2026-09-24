from datetime import datetime, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
)
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.tenant import Tenant


CURRENT_SUBSCRIPTION_STATUSES = ["trialing", "active", "past_due"]

STATUS_PROJECTION_MAP = {
    "trialing": "trial",
    "active": "active",
    "past_due": "past_due",
    "cancelled": "cancelled",
    "expired": "expired",
}


class SaaSSubscriptionService:
    def __init__(self, db: Session):
        self.db = db

    def get_current_subscription(
        self,
        tenant_id: int,
    ) -> Optional[SaaSSubscription]:
        """
        Retrieve the current active, trialing, or past_due subscription for a tenant.
        Historical states (cancelled, expired) are not returned.
        Uses deterministic ordering: created_at DESC, id DESC.
        """
        return (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.tenant_id == tenant_id,
                SaaSSubscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
            )
            .order_by(
                SaaSSubscription.created_at.desc(),
                SaaSSubscription.id.desc(),
            )
            .first()
        )

    def get_latest_subscription(
        self,
        tenant_id: int,
    ) -> Optional[SaaSSubscription]:
        """
        Retrieve the latest authoritative subscription for a tenant,
        regardless of status (trialing, active, past_due, cancelled, expired).
        Uses deterministic ordering: created_at DESC, id DESC.
        """
        return (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.tenant_id == tenant_id)
            .order_by(
                SaaSSubscription.created_at.desc(),
                SaaSSubscription.id.desc(),
            )
            .first()
        )

    def resolve_plan(
        self,
        plan_id: Optional[int] = None,
        plan_code: Optional[str] = None,
    ) -> SaaSPlan:
        """
        Resolves an authoritative active SaaSPlan.
        - If both plan_id and plan_code are provided, verifies they resolve to the same plan.
        - If neither is provided, resolves the default active plan with code 'basic'.
        - Validates that the plan exists and is active.
        """
        plan_by_id: Optional[SaaSPlan] = None
        plan_by_code: Optional[SaaSPlan] = None

        if plan_id is not None:
            plan_by_id = (
                self.db.query(SaaSPlan)
                .filter(SaaSPlan.id == plan_id)
                .first()
            )
            if not plan_by_id:
                raise NotFoundException(f"SaaS Plan with id {plan_id} not found")
            if not plan_by_id.is_active:
                raise AppException(f"SaaS Plan '{plan_by_id.name}' is inactive")

        if plan_code is not None:
            clean_code = plan_code.strip().lower()
            plan_by_code = (
                self.db.query(SaaSPlan)
                .filter(func.lower(SaaSPlan.code) == clean_code)
                .first()
            )
            if not plan_by_code:
                raise NotFoundException(f"SaaS Plan with code '{plan_code}' not found")
            if not plan_by_code.is_active:
                raise AppException(f"SaaS Plan '{plan_by_code.name}' is inactive")

        # Conflict check if both provided
        if plan_by_id is not None and plan_by_code is not None:
            if plan_by_id.id != plan_by_code.id:
                raise ConflictException(
                    f"Plan ID ({plan_id}) and Plan code ('{plan_code}') resolve to different plans"
                )
            return plan_by_id

        if plan_by_id is not None:
            return plan_by_id

        if plan_by_code is not None:
            return plan_by_code

        # Default plan fallback: active plan with code 'basic'
        default_plan = (
            self.db.query(SaaSPlan)
            .filter(
                func.lower(SaaSPlan.code) == "basic",
                SaaSPlan.is_active.is_(True),
            )
            .first()
        )
        if not default_plan:
            raise NotFoundException("Active default SaaS plan ('basic') not found")

        return default_plan

    def sync_tenant_projection(
        self,
        subscription: SaaSSubscription,
    ) -> None:
        """
        Synchronizes legacy projection columns on the Tenant model:
        - tenant.plan = plan.code
        - tenant.subscription_status = legacy-mapped status ('trial', 'active', etc.)
        - tenant.subscription_end_date = subscription.current_period_end
        """
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == subscription.tenant_id)
            .first()
        )
        if not tenant:
            raise NotFoundException(f"Tenant {subscription.tenant_id} not found")

        plan = (
            self.db.query(SaaSPlan)
            .filter(SaaSPlan.id == subscription.plan_id)
            .first()
        )
        if not plan:
            raise NotFoundException(f"SaaS Plan {subscription.plan_id} not found")

        legacy_status = STATUS_PROJECTION_MAP.get(
            subscription.status,
            subscription.status,
        )

        tenant.plan = plan.code
        tenant.subscription_status = legacy_status
        tenant.subscription_end_date = subscription.current_period_end

    def create_initial_subscription(
        self,
        tenant_id: int,
        plan_id: Optional[int] = None,
        plan_code: Optional[str] = None,
    ) -> SaaSSubscription:
        """
        Creates an initial subscription for a tenant within the caller's transaction boundary.
        1. Locks tenant row using SELECT ... FOR UPDATE.
        2. Validates tenant exists.
        3. Enforces the One Current Subscription Rule using row locking.
        4. Resolves the active SaaS plan from saas_plans (never hardcoded).
        5. Snapshots plan pricing, interval, and currency into the subscription.
        6. Calculates dates and status (trialing if trial_days > 0, active if trial_days == 0).
        7. Synchronizes legacy tenant projection.
        8. Flushes changes to the shared session (does NOT commit or rollback).
        """
        # 1. Lock tenant row
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .with_for_update()
            .first()
        )
        if not tenant:
            raise NotFoundException(f"Tenant {tenant_id} not found")

        # 2. Concurrency Safety: One Current Subscription Rule
        existing_sub = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.tenant_id == tenant_id,
                SaaSSubscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
            )
            .with_for_update()
            .first()
        )
        if existing_sub:
            raise ConflictException(
                f"Tenant {tenant_id} already has a current subscription (status: {existing_sub.status})"
            )

        # 3. Resolve active plan
        plan = self.resolve_plan(plan_id=plan_id, plan_code=plan_code)

        # 4. Calculate subscription dates and initial status
        start_date = datetime.utcnow()
        current_period_start = start_date

        if plan.trial_days > 0:
            status = "trialing"
            trial_end_date = start_date + timedelta(days=plan.trial_days)
            current_period_end = trial_end_date
        else:
            # Zero-trial plan: enters active immediately
            status = "active"
            trial_end_date = None
            if plan.billing_interval.strip().lower() == "yearly":
                current_period_end = start_date + relativedelta(years=1)
            else:
                current_period_end = start_date + relativedelta(months=1)

        # 5. Snapshot attributes and create subscription record
        subscription = SaaSSubscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status=status,
            billing_interval=plan.billing_interval,
            unit_price=plan.price,
            currency=plan.currency,
            start_date=start_date,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            trial_end_date=trial_end_date,
            cancelled_at=None,
            cancel_at_period_end=False,
        )

        self.db.add(subscription)
        self.db.flush()

        tenant.current_subscription_id = subscription.id

        # 6. Synchronize legacy tenant projection
        self.sync_tenant_projection(subscription)
        self.db.flush()

        return subscription

    def cancel_subscription(
        self,
        tenant_id: int,
        cancel_at_period_end: bool = True,
        reason: Optional[str] = None,
    ) -> SaaSSubscription:
        """
        Cancels the tenant's current subscription.
        - Enforces tenant isolation via row-locking tenant and current subscription.
        - Normal scheduled cancellation:
            * sets cancel_at_period_end = True
            * sets cancelled_at = utcnow()
            * preserves status = active
            * maintains tenant projection active
        - Terminal subscriptions (cancelled, expired) cannot be cancelled (raises 400).
        - Idempotent: repeated calls safely return existing subscription without error.
        - Flushes changes to session (caller owns commit/rollback).
        """
        # Lock tenant
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .with_for_update()
            .first()
        )
        if not tenant:
            raise NotFoundException(f"Tenant {tenant_id} not found")

        # Query and lock current subscription
        sub = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.tenant_id == tenant_id)
            .order_by(
                SaaSSubscription.created_at.desc(),
                SaaSSubscription.id.desc(),
            )
            .with_for_update()
            .first()
        )
        if not sub:
            raise NotFoundException(f"No subscription found for tenant {tenant_id}")

        if sub.status in ("cancelled", "expired"):
            raise AppException(
                f"Cannot cancel a subscription that is already '{sub.status}'"
            )

        now = datetime.utcnow()
        if not sub.cancel_at_period_end:
            sub.cancel_at_period_end = True
            if sub.cancelled_at is None:
                sub.cancelled_at = now

        self.db.flush()
        self.sync_tenant_projection(sub)
        self.db.flush()

        return sub
