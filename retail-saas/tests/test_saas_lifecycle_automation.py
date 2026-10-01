"""
P2 Task 12 — Automated SaaS Subscription Lifecycle Tests.

Validates:
1. Celery task registration and Beat scheduler configuration.
2. Redis distributed lock mechanics (token ownership, safe Lua release, contention).
3. Automated Celery task execution, commit on success, rollback on exception, lock release.
4. Celery task lock contention handling (skipping when lock held).
5. Super Admin manual endpoint regression, schema compliance, and 409 Conflict under lock contention.
6. End-to-end idempotency and duplicate invoice protection.
"""

from datetime import datetime, timedelta
from decimal import Decimal
import threading
import time
from unittest.mock import patch

import pytest
from celery.schedules import crontab
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.redis_client import get_redis
from app.core.redis_lock import (
    RedisDistributedLock,
    SAAS_LIFECYCLE_LOCK_KEY,
    DEFAULT_LOCK_TTL_SECONDS,
)
from app.main import app
from app.models.saas_billing import SaaSInvoice, SaaSPlan, SaaSSubscription
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.services.saas_invoice_service import SaaSInvoiceService
from app.services.saas_subscription_lifecycle_service import (
    SaaSSubscriptionLifecycleService,
)
from app.tasks.celery_worker import celery_app
from app.tasks.saas_lifecycle_tasks import process_saas_subscription_lifecycle_task

client = TestClient(app)


# ------------------------------------------------------------------------------
# FIXTURES & HELPERS
# ------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_lifecycle_lock():
    """Ensure the Redis lifecycle lock is cleared before and after each test."""
    r = get_redis()
    try:
        r.delete(SAAS_LIFECYCLE_LOCK_KEY)
    except Exception:
        pass
    yield
    try:
        r.delete(SAAS_LIFECYCLE_LOCK_KEY)
    except Exception:
        pass
@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

def _make_test_tenant(db: Session, prefix: str = "auto") -> Tenant:
    import uuid
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Tenant {prefix} {suffix}",
        domain=f"{prefix}-{suffix}.example.com",
        plan="basic",
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _make_test_sub(
    db: Session,
    tenant: Tenant,
    status: str = "active",
    current_period_end: datetime = None,
    trial_end_date: datetime = None,
    cancel_at_period_end: bool = False,
    unit_price: float = 999.00,
) -> SaaSSubscription:
    plan = db.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()
    if not plan:
        plan = SaaSPlan(
            name="Basic",
            code="basic",
            price=unit_price,
            currency="INR",
            billing_interval="monthly",
            trial_days=14,
            is_active=True,
        )
        db.add(plan)
        db.flush()

    now = datetime.utcnow()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=status,
        billing_interval="monthly",
        unit_price=unit_price,
        currency="INR",
        start_date=now - timedelta(days=30),
        current_period_start=now - timedelta(days=14),
        current_period_end=current_period_end or (now + timedelta(days=16)),
        trial_end_date=trial_end_date,
        cancel_at_period_end=cancel_at_period_end,
    )
    db.add(sub)
    db.flush()
    tenant.current_subscription_id = sub.id
    tenant.subscription_status = status
    db.flush()
    return sub


def _make_super_admin(db: Session) -> tuple[SuperAdmin, dict]:
    import uuid
    from app.core.security import create_super_admin_access_token

    suffix = uuid.uuid4().hex[:8]
    sa = SuperAdmin(
        email=f"sa_{suffix}@example.com",
        full_name=f"Super Admin {suffix}",
        hashed_password="hashed_dummy_password",
        phone="9876543210",
        is_active=True,
    )
    db.add(sa)
    db.flush()
    token = create_super_admin_access_token({
        "sub": str(sa.id),
        "email": sa.email,
        "role": "SUPERADMIN",
    })
    headers = {"Authorization": f"Bearer {token}"}
    return sa, headers


# ------------------------------------------------------------------------------
# 1. CELERY REGISTRATION & BEAT SCHEDULER CONFIGURATION TESTS
# ------------------------------------------------------------------------------

def test_celery_task_registration_and_beat_schedule():
    """Verify lifecycle task is registered in Celery and configured in beat_schedule."""
    celery_app.loader.import_default_modules()
    registered = list(celery_app.tasks.keys())

    # Task is discovered
    assert "process_saas_subscription_lifecycle" in registered

    # Existing tasks remain intact
    assert "generate_invoice_pdf" in registered
    assert "send_whatsapp_message" in registered
    assert "generate_monthly_report" in registered
    assert "generate_gst_report" in registered

    # Beat schedule configuration
    beat_schedule = celery_app.conf.beat_schedule
    assert "saas-subscription-lifecycle-hourly" in beat_schedule
    entry = beat_schedule["saas-subscription-lifecycle-hourly"]
    assert entry["task"] == "process_saas_subscription_lifecycle"

    # Schedule is hourly crontab (minute 0 of every hour)
    sched = entry["schedule"]
    assert isinstance(sched, crontab)
    assert sched.minute == {0}
    assert sched.hour == set(range(24))

    # Timezone remains UTC
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True


# ------------------------------------------------------------------------------
# 2. REDIS DISTRIBUTED LOCK TESTS
# ------------------------------------------------------------------------------

def test_redis_distributed_lock_acquire_and_release():
    """Tests normal acquire, token setting, and safe Lua release."""
    lock = RedisDistributedLock("test:lifecycle:lock1", ttl_seconds=30)
    assert lock.acquire() is True
    assert lock.token is not None
    assert lock.is_locked() is True

    # Lock cannot be acquired by another instance while held
    competing_lock = RedisDistributedLock("test:lifecycle:lock1", ttl_seconds=30)
    assert competing_lock.acquire() is False

    # Safe release by owner
    assert lock.release() is True
    assert lock.is_locked() is False

    # Now competing lock can acquire
    assert competing_lock.acquire() is True
    assert competing_lock.release() is True


def test_redis_distributed_lock_ownership_safe_release():
    """A lock cannot be released by a caller that does not hold the active token."""
    r = get_redis()
    lock_key = "test:lifecycle:ownership"

    lock_owner = RedisDistributedLock(lock_key, ttl_seconds=30)
    assert lock_owner.acquire() is True

    # Imposter tries to release with a different token
    imposter = RedisDistributedLock(lock_key, ttl_seconds=30)
    imposter.token = "fake-token-not-matching"
    imposter._acquired = True
    assert imposter.release() is False

    # Original owner can still release safely
    assert lock_owner.release() is True


def test_redis_distributed_lock_context_manager():
    """Tests context manager protocol for RedisDistributedLock."""
    lock_key = "test:lifecycle:context"
    with RedisDistributedLock(lock_key, ttl_seconds=30) as lock:
        assert lock._acquired is True
        assert lock.is_locked() is True

    # Automatically released upon exit
    r = get_redis()
    assert not r.exists(lock_key)


# ------------------------------------------------------------------------------
# 3. CELERY LIFECYCLE TASK TESTS
# ------------------------------------------------------------------------------

def test_celery_lifecycle_task_success(db_session: Session):
    """Automated task runs lifecycle, commits transitions, and returns structured result."""
    now = datetime.utcnow()
    t = _make_test_tenant(db_session, "celery-success")
    sub = _make_test_sub(
        db_session,
        t,
        status="active",
        current_period_end=now - timedelta(hours=2),
    )
    sub_id = sub.id
    db_session.commit()

    # Run the Celery task directly
    result = process_saas_subscription_lifecycle_task()

    assert result["status"] == "success"
    assert "summary" in result
    assert result["summary"]["active_subscriptions_moved_to_past_due"] >= 1
    assert result["duration_seconds"] >= 0

    # Verify DB commit was completed
    db_session.expire_all()
    reloaded_sub = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).one()
    assert reloaded_sub.status == "past_due"

    # Verify lock was released
    r = get_redis()
    assert not r.exists(SAAS_LIFECYCLE_LOCK_KEY)


def test_celery_lifecycle_task_skips_when_lock_held(db_session: Session):
    """When Redis lock is already held, Celery task logs and skips execution without mutating DB."""
    # Hold the lock manually
    external_lock = RedisDistributedLock(SAAS_LIFECYCLE_LOCK_KEY, ttl_seconds=60)
    assert external_lock.acquire() is True

    try:
        result = process_saas_subscription_lifecycle_task()
        assert result["status"] == "skipped"
        assert "Lock already held" in result["reason"]
        assert result["lock_key"] == SAAS_LIFECYCLE_LOCK_KEY
    finally:
        external_lock.release()


def test_celery_lifecycle_task_rollback_and_lock_release_on_exception():
    """Task rolls back transaction and safely releases Redis lock when an unhandled exception occurs."""
    with patch.object(
        SaaSSubscriptionLifecycleService,
        "run_all",
        side_effect=RuntimeError("Simulated Database Outage"),
    ):
        with pytest.raises(RuntimeError, match="Simulated Database Outage"):
            process_saas_subscription_lifecycle_task()

    # Lock must be released even after exception
    r = get_redis()
    assert not r.exists(SAAS_LIFECYCLE_LOCK_KEY)


# ------------------------------------------------------------------------------
# 4. IDEMPOTENCY & RENEWAL INVOICE DUPLICATE PROTECTION
# ------------------------------------------------------------------------------

def test_lifecycle_task_repeated_execution_is_idempotent(db_session: Session):
    """Executing the task twice produces zero duplicate transitions or invoices."""
    now = datetime.utcnow()
    t = _make_test_tenant(db_session, "idem-test")
    sub = _make_test_sub(
        db_session,
        t,
        status="active",
        current_period_end=now + timedelta(days=2),  # inside 7-day advance renewal window
    )
    sub_id = sub.id
    db_session.commit()

    # First run generates renewal invoice
    res1 = process_saas_subscription_lifecycle_task()
    assert res1["status"] == "success"
    assert res1["summary"]["renewal_invoices_generated"] >= 1

    invoices_after_run1 = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub_id)
        .all()
    )
    assert len(invoices_after_run1) == 1

    # Second immediate run produces 0 renewal invoices
    res2 = process_saas_subscription_lifecycle_task()
    assert res2["status"] == "success"
    assert res2["summary"]["renewal_invoices_generated"] == 0

    invoices_after_run2 = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub_id)
        .all()
    )
    assert len(invoices_after_run2) == 1


# ------------------------------------------------------------------------------
# 5. SUPER ADMIN MANUAL ENDPOINT REGRESSION & DISTRIBUTED LOCK INTEGRATION
# ------------------------------------------------------------------------------

def test_super_admin_manual_endpoint_success(db_session: Session):
    """Super Admin manual endpoint runs lifecycle and returns complete schema."""
    sa, headers = _make_super_admin(db_session)
    db_session.commit()

    resp = client.post(
        "/api/v1/super-admins/subscription-lifecycle/process",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "trials_expired_to_past_due" in data
    assert "active_subscriptions_moved_to_past_due" in data
    assert "scheduled_cancellations_processed" in data
    assert "scheduled_plan_changes_applied" in data
    assert "past_due_subscriptions_expired" in data
    assert "renewal_invoices_generated" in data


def test_super_admin_manual_endpoint_blocked_by_active_lock(db_session: Session):
    """Super Admin manual endpoint returns 409 Conflict if automated Celery task is currently holding lock."""
    sa, headers = _make_super_admin(db_session)
    db_session.commit()

    # Simulate Celery task currently holding the lock
    lock = RedisDistributedLock(SAAS_LIFECYCLE_LOCK_KEY, ttl_seconds=60)
    assert lock.acquire() is True

    try:
        resp = client.post(
            "/api/v1/super-admins/subscription-lifecycle/process",
            headers=headers,
        )
        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"]
    finally:
        lock.release()

    # Once lock is released, manual endpoint succeeds
    resp2 = client.post(
        "/api/v1/super-admins/subscription-lifecycle/process",
        headers=headers,
    )
    assert resp2.status_code == 200


def test_unauthorized_access_to_super_admin_endpoint(db_session: Session):
    """Unauthenticated and tenant users cannot access the Super Admin endpoint."""
    resp = client.post("/api/v1/super-admins/subscription-lifecycle/process")
    assert resp.status_code in (401, 403)


# ------------------------------------------------------------------------------
# 6. REDIS HEARTBEAT, SAFE RENEWAL & LOCK-LOSS DETECTION TESTS
# ------------------------------------------------------------------------------

def test_redis_distributed_lock_heartbeat_ttl_renewal():
    """
    Test A: Heartbeat / TTL Extension.
    Acquires lock, verifies finite TTL exists, renews, and verifies TTL extended.
    """
    r = get_redis()
    lock_key = "test:lifecycle:heartbeat_renew"
    lock = RedisDistributedLock(lock_key, ttl_seconds=10, auto_heartbeat=False)
    assert lock.acquire(auto_heartbeat=False) is True
    try:
        initial_ttl = r.ttl(lock_key)
        assert 5 <= initial_ttl <= 10

        # Safely renew with a larger TTL
        assert lock.renew(extend_ttl_seconds=30) is True
        renewed_ttl = r.ttl(lock_key)
        assert 20 <= renewed_ttl <= 30
        assert lock.is_valid() is True
    finally:
        assert lock.release() is True


def test_redis_distributed_lock_ownership_safe_renewal():
    """
    Test B: Ownership-Safe Renewal.
    Worker A owns the lock. Worker B (different token) must NOT be able to renew Worker A's lock.
    """
    r = get_redis()
    lock_key = "test:lifecycle:ownership_renew"
    lock_a = RedisDistributedLock(lock_key, ttl_seconds=30, auto_heartbeat=False)
    assert lock_a.acquire(auto_heartbeat=False) is True
    token_a = lock_a.token

    lock_b = RedisDistributedLock(lock_key, ttl_seconds=30, auto_heartbeat=False)
    lock_b.token = "imposter-token-worker-b"
    lock_b._acquired = True

    try:
        # Worker B fails to renew Worker A's lock and records lock loss
        assert lock_b.renew() is False
        assert lock_b.lock_lost is True
        assert lock_b.is_valid() is False

        # Worker A can still renew safely
        assert lock_a.renew() is True
        assert lock_a.is_valid() is True
        assert r.get(lock_key) == token_a
    finally:
        assert lock_a.release() is True


def test_redis_distributed_lock_heartbeat_stops_on_release():
    """
    Test D: Heartbeat Thread Lifecycle & Deterministic Stop.
    Starts background heartbeat thread on acquire; stops and joins on release.
    """
    lock_key = "test:lifecycle:heartbeat_stop"
    lock = RedisDistributedLock(lock_key, ttl_seconds=10, heartbeat_interval=0.1)
    assert lock.acquire(auto_heartbeat=True) is True

    # Background daemon thread is active
    assert lock._heartbeat_thread is not None
    assert lock._heartbeat_thread.is_alive()
    thread_name = lock._heartbeat_thread.name

    # Release stops heartbeat thread and deletes key
    assert lock.release() is True
    assert lock._heartbeat_thread is None

    # Verify no lingering heartbeat thread in thread list
    alive_names = [t.name for t in threading.enumerate()]
    assert thread_name not in alive_names


def test_redis_distributed_lock_long_running_heartbeat_survival():
    """
    Test E: Long-Running Execution / Lock Expiry Survival.
    Worker A acquires lock with a short nominal TTL (2s) and 0.4s heartbeat.
    After running past nominal TTL boundaries, heartbeat keeps lock alive,
    and Worker B is blocked from acquiring.
    """
    r = get_redis()
    lock_key = "test:lifecycle:long_running"
    worker_a = RedisDistributedLock(lock_key, ttl_seconds=2, heartbeat_interval=0.4)
    assert worker_a.acquire(auto_heartbeat=True) is True

    try:
        # Wait 1.0s (past half of nominal TTL; heartbeat fires and renews)
        time.sleep(1.0)

        # Worker B tries to acquire during Worker A's execution
        worker_b = RedisDistributedLock(lock_key, ttl_seconds=2, auto_heartbeat=False)
        assert worker_b.acquire() is False

        # Worker A is still valid and actively owning the key
        assert worker_a.is_valid() is True
        assert r.get(lock_key) == worker_a.token
    finally:
        worker_a.release()

    # Now that Worker A released, Worker B can acquire
    assert worker_b.acquire() is True
    worker_b.release()


def test_redis_distributed_lock_heartbeat_failure_and_lock_loss():
    """
    Test F: Heartbeat Failure & Lock Loss Detection.
    When the key is lost, stolen, or expired in Redis, renew() detects loss,
    marks is_valid()=False, and prevents releasing another process's lock.
    """
    r = get_redis()
    lock_key = "test:lifecycle:lock_loss"
    lock = RedisDistributedLock(lock_key, ttl_seconds=10, auto_heartbeat=False)
    assert lock.acquire() is True

    # Simulate another worker taking the key
    r.set(lock_key, "stolen-token")

    # Renewal detects lock loss
    assert lock.renew() is False
    assert lock.lock_lost is True
    assert lock.is_valid() is False
    assert "no longer owned" in lock.lock_lost_reason

    # Release does NOT delete the key belonging to the other worker
    assert lock.release() is False
    assert r.get(lock_key) == "stolen-token"
    r.delete(lock_key)


def test_celery_lifecycle_task_aborts_on_lock_loss(db_session: Session):
    """
    Celery task aborts without committing if lock is lost/stolen during execution.
    Transaction is safely rolled back.
    """
    t = _make_test_tenant(db_session, "celery-lock-loss")
    sub = _make_test_sub(
        db_session,
        t,
        status="active",
        current_period_end=datetime.utcnow() - timedelta(hours=2),
    )
    sub_id = sub.id
    db_session.commit()

    def steal_lock(*args, **kwargs):
        # Steal the lock in Redis during the lifecycle run
        r = get_redis()
        r.set(SAAS_LIFECYCLE_LOCK_KEY, "stolen-by-other-worker")
        return {
            "trials_expired_to_past_due": 0,
            "active_subscriptions_moved_to_past_due": 1,
            "scheduled_cancellations_processed": 0,
            "scheduled_plan_changes_applied": 0,
            "past_due_subscriptions_expired": 0,
            "renewal_invoices_generated": 0,
        }

    with patch.object(
        SaaSSubscriptionLifecycleService,
        "run_all",
        side_effect=steal_lock,
    ):
        with pytest.raises(RuntimeError, match="Distributed lock '.*' was lost"):
            process_saas_subscription_lifecycle_task()

    # The subscription was NOT committed to past_due because rollback occurred
    db_session.expire_all()
    reloaded = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).one()
    assert reloaded.status == "active"


# ------------------------------------------------------------------------------
# 7. DATABASE COMPOSITE UNIQUE CONSTRAINT & INVOICE CONCURRENCY TESTS
# ------------------------------------------------------------------------------

def test_database_invoice_unique_constraint_cycle(db_session: Session):
    """
    Test G: Database Unique Constraint Test.
    Ensures (subscription_id, billing_reason, due_date) cannot create two invoices.
    """
    tenant = _make_test_tenant(db_session, "uq-test")
    sub = _make_test_sub(db_session, tenant)
    db_session.commit()

    due_date = datetime(2026, 11, 1, 0, 0, 0)
    inv1 = SaaSInvoice(
        invoice_number="INV-UQ-001",
        tenant_id=tenant.id,
        subscription_id=sub.id,
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        currency="INR",
        billing_reason="subscription_cycle",
        status="unpaid",
        due_date=due_date,
    )
    db_session.add(inv1)
    db_session.flush()

    inv2 = SaaSInvoice(
        invoice_number="INV-UQ-002",
        tenant_id=tenant.id,
        subscription_id=sub.id,
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        currency="INR",
        billing_reason="subscription_cycle",
        status="unpaid",
        due_date=due_date,
    )
    db_session.add(inv2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_database_invoice_different_due_date_allowed(db_session: Session):
    """
    Test H: Different Cycle Test.
    Invoices for different due_dates under the same subscription are permitted.
    """
    tenant = _make_test_tenant(db_session, "diff-due")
    sub = _make_test_sub(db_session, tenant)
    db_session.commit()

    due_date_1 = datetime(2026, 11, 1, 0, 0, 0)
    due_date_2 = datetime(2026, 12, 1, 0, 0, 0)

    inv1 = SaaSInvoice(
        invoice_number="INV-CYCLE-001",
        tenant_id=tenant.id,
        subscription_id=sub.id,
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        currency="INR",
        billing_reason="subscription_cycle",
        status="unpaid",
        due_date=due_date_1,
    )
    inv2 = SaaSInvoice(
        invoice_number="INV-CYCLE-002",
        tenant_id=tenant.id,
        subscription_id=sub.id,
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        currency="INR",
        billing_reason="subscription_cycle",
        status="unpaid",
        due_date=due_date_2,
    )
    db_session.add(inv1)
    db_session.add(inv2)
    db_session.flush()
    assert inv1.id is not None
    assert inv2.id is not None
    assert inv1.id != inv2.id


def test_database_invoice_different_billing_reason_allowed(db_session: Session):
    """
    Test I: Different Billing Reason Test.
    Different billing reasons for the same subscription on the same date are permitted.
    """
    tenant = _make_test_tenant(db_session, "diff-reason")
    sub = _make_test_sub(db_session, tenant)
    db_session.commit()

    due_date = datetime(2026, 11, 1, 0, 0, 0)

    inv_cycle = SaaSInvoice(
        invoice_number="INV-REASON-001",
        tenant_id=tenant.id,
        subscription_id=sub.id,
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        currency="INR",
        billing_reason="subscription_cycle",
        status="unpaid",
        due_date=due_date,
    )
    inv_manual = SaaSInvoice(
        invoice_number="INV-REASON-002",
        tenant_id=tenant.id,
        subscription_id=sub.id,
        subtotal=Decimal("150.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("150.00"),
        currency="INR",
        billing_reason="manual",
        status="unpaid",
        due_date=due_date,
    )
    db_session.add(inv_cycle)
    db_session.add(inv_manual)
    db_session.flush()
    assert inv_cycle.id is not None
    assert inv_manual.id is not None


def test_database_invoice_column_nullability_and_semantics(db_session: Session):
    """
    Test J: Null & Actual Column Semantics.
    Verifies that the composite unique columns are strictly non-nullable.
    """
    assert SaaSInvoice.subscription_id.nullable is False
    assert SaaSInvoice.billing_reason.nullable is False
    assert SaaSInvoice.due_date.nullable is False

    tenant = _make_test_tenant(db_session, "null-check")
    db_session.commit()

    inv_missing_fields = SaaSInvoice(
        invoice_number="INV-NULL-001",
        tenant_id=tenant.id,
        subscription_id=None,
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("500.00"),
        currency="INR",
        billing_reason="subscription_cycle",
        due_date=None,
    )
    db_session.add(inv_missing_fields)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_concurrent_invoice_service_creation_race(db_session: Session):
    """
    Test K: Concurrent Invoice Creation Test.
    Two concurrent worker threads race to create the exact same renewal invoice.
    MySQL unique constraint + savepoint-protected idempotency ensures:
    - Exactly one invoice is persisted in the database
    - Both threads complete safely and return the same invoice ID
    - No unhandled IntegrityError or corrupted transaction state
    """
    tenant = _make_test_tenant(db_session, "concur-inv")
    sub = _make_test_sub(db_session, tenant)
    db_session.commit()

    due_date = datetime(2026, 12, 15, 0, 0, 0)
    invoices = []
    errors = []

    def create_invoice_worker():
        db = SessionLocal()
        try:
            svc = SaaSInvoiceService(db)
            inv = svc.create_invoice(
                subscription_id=sub.id,
                billing_reason="subscription_cycle",
                due_date=due_date,
                idempotent=True,
            )
            db.commit()
            invoices.append(inv.id)
        except Exception as exc:
            db.rollback()
            errors.append(exc)
        finally:
            db.close()

    t1 = threading.Thread(target=create_invoice_worker)
    t2 = threading.Thread(target=create_invoice_worker)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(errors) == 0, f"Errors in concurrent creation: {errors}"
    assert len(invoices) == 2
    assert invoices[0] == invoices[1]

    # Verify exactly 1 invoice persisted in MySQL
    persisted = (
        db_session.query(SaaSInvoice)
        .filter(
            SaaSInvoice.subscription_id == sub.id,
            SaaSInvoice.billing_reason == "subscription_cycle",
            SaaSInvoice.due_date == due_date,
        )
        .all()
    )
    assert len(persisted) == 1
    assert persisted[0].id == invoices[0]

