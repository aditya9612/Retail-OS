from datetime import datetime, timedelta
import threading
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.saas_billing import SaaSInvoice, SaaSSubscription
from app.services.saas_invoice_service import SaaSInvoiceService
from app.services.saas_subscription_service import SaaSSubscriptionService

settings = get_settings()
_renewal_mutex = threading.Lock()


class SaaSSubscriptionLifecycleService:
    """
    Authoritative service managing SaaS subscription lifecycle transitions:
    - Trial expiration (trialing -> past_due)
    - Scheduled cancellation (active + cancel_at_period_end -> cancelled)
    - Active period expiration (active -> past_due)
    - Grace period expiration (past_due -> expired)
    - Proactive renewal invoice generation
    - Tenant projection synchronization

    Conventions:
    - Caller owns transaction boundaries; this service flushes changes but does not commit or rollback.
    - Idempotent: repeated runs are no-ops once state transitions are applied.
    - Atomic conditional updates prevent race conditions across concurrent workers.
    """

    def __init__(
        self,
        db: Session,
        grace_period_days: Optional[int] = None,
        invoice_advance_days: Optional[int] = None,
    ):
        self.db = db
        self.grace_period_days = (
            grace_period_days
            if grace_period_days is not None
            else settings.SAAS_SUBSCRIPTION_GRACE_PERIOD_DAYS
        )
        self.invoice_advance_days = (
            invoice_advance_days
            if invoice_advance_days is not None
            else settings.SAAS_INVOICE_ADVANCE_DAYS
        )
        self.subscription_service = SaaSSubscriptionService(db)
        self.invoice_service = SaaSInvoiceService(db)

    def expire_trials(self, tenant_id: Optional[int] = None) -> int:
        """
        Transitions trialing subscriptions whose trial_end_date <= now to 'past_due'.
        Does NOT transition directly to 'expired' (grace period applies).

        Returns the number of subscriptions transitioned.
        """
        now = datetime.utcnow()
        query = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.status == "trialing",
                SaaSSubscription.trial_end_date.isnot(None),
                SaaSSubscription.trial_end_date <= now,
            )
        )
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)

        try:
            candidates = query.with_for_update(skip_locked=True).all()
        except Exception:
            candidates = query.all()

        transitioned_count = 0
        for sub in candidates:
            # Atomic conditional update prevents double-transitions across concurrent workers
            rows_updated = (
                self.db.query(SaaSSubscription)
                .filter(
                    SaaSSubscription.id == sub.id,
                    SaaSSubscription.status == "trialing",
                    SaaSSubscription.trial_end_date.isnot(None),
                    SaaSSubscription.trial_end_date <= now,
                )
                .update(
                    {SaaSSubscription.status: "past_due"},
                    synchronize_session="fetch",
                )
            )

            if rows_updated > 0:
                sub.status = "past_due"
                self.subscription_service.sync_tenant_projection(sub)
                transitioned_count += 1

        self.db.flush()
        return transitioned_count

    def process_scheduled_cancellations(self, tenant_id: Optional[int] = None) -> int:
        """
        Transitions active subscriptions where cancel_at_period_end == True and
        current_period_end <= now directly to 'cancelled'.

        CRITICAL:
        - Prevents scheduled cancellations from transitioning to 'past_due'.
        - Subscriptions remain 'active' until current_period_end is reached.
        - Synchronizes tenant projection to 'cancelled'.
        """
        now = datetime.utcnow()
        query = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.status == "active",
                SaaSSubscription.cancel_at_period_end.is_(True),
                SaaSSubscription.current_period_end <= now,
            )
        )
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)

        try:
            candidates = query.with_for_update(skip_locked=True).all()
        except Exception:
            candidates = query.all()

        cancelled_count = 0
        for sub in candidates:
            rows_updated = (
                self.db.query(SaaSSubscription)
                .filter(
                    SaaSSubscription.id == sub.id,
                    SaaSSubscription.status == "active",
                    SaaSSubscription.cancel_at_period_end.is_(True),
                    SaaSSubscription.current_period_end <= now,
                )
                .update(
                    {SaaSSubscription.status: "cancelled"},
                    synchronize_session="fetch",
                )
            )

            if rows_updated > 0:
                sub.status = "cancelled"
                self.subscription_service.sync_tenant_projection(sub)
                cancelled_count += 1

        self.db.flush()
        return cancelled_count

    def process_scheduled_plan_changes(self, tenant_id: Optional[int] = None) -> int:
        """
        Applies scheduled plan changes (downgrades) whose current_period_end <= now.
        - Identifies subscriptions where scheduled_plan_id IS NOT NULL and current_period_end <= now.
        - Locks tenant row and subscription row.
        - Validates scheduled target plan.
        - Mutates subscription:
            sub.plan_id = target_plan.id
            sub.unit_price = target_plan.price
            sub.billing_interval = target_plan.billing_interval
            sub.currency = target_plan.currency
            sub.scheduled_plan_id = None
        - Advances period continuously:
            old_period_end = sub.current_period_end
            sub.current_period_start = old_period_end
            sub.current_period_end = old_period_end + (1 year if yearly else 1 month)
        - Preserves Tenant.current_subscription_id and syncs legacy projection.
        - Idempotent: repeated runs are no-ops since scheduled_plan_id is cleared.
        """
        now = datetime.utcnow()
        query = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.scheduled_plan_id.isnot(None),
                SaaSSubscription.current_period_end <= now,
            )
        )
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)

        try:
            candidates = query.with_for_update(skip_locked=True).all()
        except Exception:
            candidates = query.all()

        applied_count = 0
        from app.models.saas_billing import SaaSPlan
        from app.models.tenant import Tenant
        from dateutil.relativedelta import relativedelta

        for sub in candidates:
            if not sub.scheduled_plan_id:
                continue

            target_plan = (
                self.db.query(SaaSPlan)
                .filter(SaaSPlan.id == sub.scheduled_plan_id)
                .first()
            )
            if not target_plan:
                continue

            # Lock tenant row
            tenant = (
                self.db.query(Tenant)
                .filter(Tenant.id == sub.tenant_id)
                .with_for_update()
                .first()
            )

            # Apply scheduled plan change
            sub.plan_id = target_plan.id
            sub.unit_price = target_plan.price
            sub.billing_interval = target_plan.billing_interval
            sub.currency = target_plan.currency
            sub.scheduled_plan_id = None

            # Advance period continuously
            old_period_end = sub.current_period_end
            sub.current_period_start = old_period_end
            if sub.billing_interval.strip().lower() == "yearly":
                sub.current_period_end = old_period_end + relativedelta(years=1)
            else:
                sub.current_period_end = old_period_end + relativedelta(months=1)

            # Keep authoritative pointer consistent
            if tenant:
                tenant.current_subscription_id = sub.id

            self.subscription_service.sync_tenant_projection(sub)
            applied_count += 1

        self.db.flush()
        return applied_count

    def process_period_ends(self, tenant_id: Optional[int] = None) -> int:
        """
        Transitions active subscriptions whose current_period_end <= now to 'past_due'.

        IMPORTANT:
        - Only processes records where cancel_at_period_end is False and scheduled_plan_id is None.
        - Subscriptions with cancel_at_period_end == True are left untouched for cancellation processing.
        - Subscriptions with scheduled_plan_id != None are handled by process_scheduled_plan_changes.

        Returns the number of subscriptions transitioned.
        """
        now = datetime.utcnow()
        query = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.status == "active",
                SaaSSubscription.cancel_at_period_end.is_(False),
                SaaSSubscription.scheduled_plan_id.is_(None),
                SaaSSubscription.current_period_end <= now,
            )
        )
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)

        try:
            candidates = query.with_for_update(skip_locked=True).all()
        except Exception:
            candidates = query.all()

        transitioned_count = 0
        for sub in candidates:
            # Atomic conditional update
            rows_updated = (
                self.db.query(SaaSSubscription)
                .filter(
                    SaaSSubscription.id == sub.id,
                    SaaSSubscription.status == "active",
                    SaaSSubscription.cancel_at_period_end.is_(False),
                    SaaSSubscription.scheduled_plan_id.is_(None),
                    SaaSSubscription.current_period_end <= now,
                )
                .update(
                    {SaaSSubscription.status: "past_due"},
                    synchronize_session="fetch",
                )
            )

            if rows_updated > 0:
                sub.status = "past_due"
                self.subscription_service.sync_tenant_projection(sub)
                transitioned_count += 1

        self.db.flush()
        return transitioned_count

    def expire_grace_periods(self, tenant_id: Optional[int] = None) -> int:
        """
        Transitions past_due subscriptions to 'expired' once the grace boundary is reached (now >= boundary).

        Boundaries:
        - For trial-originated past_due: boundary = trial_end_date + grace_period
          (trial_end_date is set and current_period_end <= trial_end_date)
        - For paid-cycle past_due: boundary = current_period_end + grace_period
          (trial_end_date is None or current_period_end > trial_end_date)

        Returns the number of subscriptions expired.
        """
        now = datetime.utcnow()
        grace_delta = timedelta(days=self.grace_period_days)

        query = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.status == "past_due")
        )
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)

        try:
            candidates = query.with_for_update(skip_locked=True).all()
        except Exception:
            candidates = query.all()

        expired_count = 0
        for sub in candidates:
            # Determine appropriate grace boundary
            if sub.trial_end_date is not None and sub.current_period_end <= sub.trial_end_date:
                boundary = sub.trial_end_date + grace_delta
            else:
                boundary = sub.current_period_end + grace_delta

            if now >= boundary:
                rows_updated = (
                    self.db.query(SaaSSubscription)
                    .filter(
                        SaaSSubscription.id == sub.id,
                        SaaSSubscription.status == "past_due",
                    )
                    .update(
                        {SaaSSubscription.status: "expired"},
                        synchronize_session="fetch",
                    )
                )

                if rows_updated > 0:
                    sub.status = "expired"
                    self.subscription_service.sync_tenant_projection(sub)
                    expired_count += 1

        self.db.flush()
        return expired_count

    def generate_upcoming_renewal_invoices(self, tenant_id: Optional[int] = None) -> int:
        """
        Proactively generates renewal invoices for upcoming subscription cycles.

        Rules:
        - Eligible statuses: 'active', 'past_due'.
        - cancel_at_period_end must be False.
        - Window: now >= current_period_end - invoice_advance_days (current_period_end <= now + advance_days).
        - Cycle identity: subscription_id + billing_reason='subscription_cycle' + due_date=current_period_end.
        - If cycle invoice already exists (paid or unpaid), reuses it and creates zero duplicates.
        - Thread/worker concurrency safe via mutex and row locking.
        """
        now = datetime.utcnow()
        advance_cutoff = now + timedelta(days=self.invoice_advance_days)

        query = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.status.in_(["active", "past_due"]),
                SaaSSubscription.cancel_at_period_end.is_(False),
                SaaSSubscription.current_period_end <= advance_cutoff,
            )
        )
        if tenant_id is not None:
            query = query.filter(SaaSSubscription.tenant_id == tenant_id)

        try:
            candidates = query.with_for_update(skip_locked=True).all()
        except Exception:
            candidates = query.all()

        generated_count = 0
        with _renewal_mutex:
            for sub in candidates:
                # Cycle identity: check if an invoice for this cycle already exists
                existing_invoice = (
                    self.db.query(SaaSInvoice)
                    .filter(
                        SaaSInvoice.subscription_id == sub.id,
                        SaaSInvoice.billing_reason == "subscription_cycle",
                        SaaSInvoice.due_date == sub.current_period_end,
                    )
                    .first()
                )
                if existing_invoice:
                    continue

                # Generate renewal invoice using snapshot from SaaSSubscription
                self.invoice_service.create_invoice(
                    subscription_id=sub.id,
                    billing_reason="subscription_cycle",
                    due_date=sub.current_period_end,
                    notes=f"Renewal invoice for billing cycle ending {sub.current_period_end.strftime('%Y-%m-%d')}",
                    idempotent=True,
                )
                generated_count += 1

        self.db.flush()
        return generated_count

    def run_all(self, tenant_id: Optional[int] = None) -> dict:
        """
        Executes all lifecycle phases in deterministic order:
        1. expire_trials()
        2. process_scheduled_cancellations()
        3. process_scheduled_plan_changes()
        4. process_period_ends()
        5. expire_grace_periods()
        6. generate_upcoming_renewal_invoices()

        Returns execution summary counts.
        """
        trials_count = self.expire_trials(tenant_id=tenant_id)
        cancellations_count = self.process_scheduled_cancellations(tenant_id=tenant_id)
        scheduled_changes_count = self.process_scheduled_plan_changes(tenant_id=tenant_id)
        active_count = self.process_period_ends(tenant_id=tenant_id)
        expired_count = self.expire_grace_periods(tenant_id=tenant_id)
        renewal_invoices_count = self.generate_upcoming_renewal_invoices(tenant_id=tenant_id)

        return {
            "trials_expired_to_past_due": trials_count,
            "active_subscriptions_moved_to_past_due": active_count,
            "scheduled_cancellations_processed": cancellations_count,
            "scheduled_plan_changes_applied": scheduled_changes_count,
            "past_due_subscriptions_expired": expired_count,
            "renewal_invoices_generated": renewal_invoices_count,
        }
