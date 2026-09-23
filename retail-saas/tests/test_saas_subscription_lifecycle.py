from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
import uuid
import pytest
from fastapi.testclient import TestClient
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.core.security import create_access_token, create_super_admin_access_token
from app.main import app
from app.models.role import Role
from app.models.saas_billing import SaaSInvoice, SaaSPlan, SaaSSubscription, SaaSUPITransaction
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.super_admin import SuperAdminCreate
from app.scripts.process_subscription_lifecycle import main as cli_lifecycle_main
from app.services.auth_service import AuthService
from app.services.saas_invoice_service import SaaSInvoiceService
from app.services.saas_subscription_lifecycle_service import SaaSSubscriptionLifecycleService
from app.services.saas_subscription_service import (
    CURRENT_SUBSCRIPTION_STATUSES,
    STATUS_PROJECTION_MAP,
    SaaSSubscriptionService,
)
from app.services.saas_upi_service import SaaSUPIService
from app.services.super_admin_service import SuperAdminService

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def ensure_baseline_plans(db_session: Session):
    """Ensure baseline plans exist in test database session."""
    plan_codes = {p.code for p in db_session.query(SaaSPlan).all()}
    plans_to_add = []
    if "basic" not in plan_codes:
        plans_to_add.append(
            SaaSPlan(
                name="Basic",
                code="basic",
                description="Essential retail management for single store operations.",
                price=Decimal("999.00"),
                currency="INR",
                billing_interval="monthly",
                trial_days=14,
                is_active=True,
            )
        )
    if "pro" not in plan_codes:
        plans_to_add.append(
            SaaSPlan(
                name="Pro",
                code="pro",
                description="Advanced multi-store management, analytics, and delivery integrations.",
                price=Decimal("2499.00"),
                currency="INR",
                billing_interval="monthly",
                trial_days=14,
                is_active=True,
            )
        )
    if "enterprise" not in plan_codes:
        plans_to_add.append(
            SaaSPlan(
                name="Enterprise",
                code="enterprise",
                description="Full platform capabilities with custom store limits and dedicated support.",
                price=Decimal("4999.00"),
                currency="INR",
                billing_interval="monthly",
                trial_days=0,
                is_active=True,
            )
        )
    if plans_to_add:
        db_session.add_all(plans_to_add)
        db_session.commit()


# ==============================================================================
# 1. REGISTRATION INTEGRATION & DEFAULT PLAN RESOLUTION
# ==============================================================================

def test_registration_creates_subscription_and_syncs_projection(db_session: Session, ensure_baseline_plans):
    """
    Test 1: New tenant registration creates exactly:
    - 1 tenant
    - 1 admin user
    - 1 SaaSSubscription
    and synchronizes the tenant projection with the active default 'basic' plan.
    """
    uid = uuid.uuid4().hex[:8]
    email = f"owner-{uid}@lifecyclecorp.com"
    domain = f"corp-{uid}"

    reg_payload = {
        "tenant_name": f"Lifecycle Corp {uid}",
        "domain": domain,
        "email": email,
        "admin_name": "Lifecycle Owner",
        "password": "Password123!",
        "phone": "9876543210",
    }

    resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    tenant_id = data["tenant_id"]

    # 1. Verify tenant was created
    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
    assert tenant is not None
    assert tenant.name == f"Lifecycle Corp {uid}"
    assert tenant.domain == domain

    # 2. Verify exactly 1 user was created
    users = db_session.query(User).filter(User.tenant_id == tenant_id).all()
    assert len(users) == 1
    assert users[0].email == email

    # 3. Verify exactly 1 SaaSSubscription was created
    subs = db_session.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == tenant_id).all()
    assert len(subs) == 1
    sub = subs[0]

    # Verify default Basic plan was loaded from DB
    basic_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()
    assert sub.plan_id == basic_plan.id
    assert sub.status == "trialing"
    assert sub.unit_price == basic_plan.price
    assert sub.billing_interval == basic_plan.billing_interval
    assert sub.currency == basic_plan.currency
    assert sub.trial_end_date is not None

    # 4. Verify tenant projection was synchronized
    assert tenant.plan == "basic"
    assert tenant.subscription_status == "trial"  # Legacy mapped from 'trialing'
    assert tenant.subscription_end_date == sub.current_period_end


def test_default_plan_resolution_loads_from_database(db_session: Session, ensure_baseline_plans):
    """
    Test 2: Verifies that plan details are dynamically read from saas_plans,
    not from hardcoded pricing constants.
    """
    svc = SaaSSubscriptionService(db_session)
    plan = svc.resolve_plan()
    assert plan is not None
    assert plan.code == "basic"
    assert plan.is_active is True
    # Confirm it has real DB scalar values
    assert isinstance(plan.price, Decimal)
    assert isinstance(plan.trial_days, int)
    assert plan.billing_interval in ("monthly", "yearly")


# ==============================================================================
# 2. EXPLICIT PLAN RESOLUTION & CONFLICT HANDLING
# ==============================================================================

def test_explicit_plan_resolution(db_session: Session, ensure_baseline_plans):
    """
    Test 3:
    - Test valid plan_id
    - Test valid plan_code
    - Test both matching
    - Test conflicting plan_id and plan_code
    """
    svc = SaaSSubscriptionService(db_session)
    basic_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()
    pro_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "pro").first()

    # 1. By plan_id
    resolved_by_id = svc.resolve_plan(plan_id=pro_plan.id)
    assert resolved_by_id.id == pro_plan.id

    # 2. By plan_code
    resolved_by_code = svc.resolve_plan(plan_code="pro")
    assert resolved_by_code.id == pro_plan.id

    # 3. Both matching
    resolved_matching = svc.resolve_plan(plan_id=pro_plan.id, plan_code="pro")
    assert resolved_matching.id == pro_plan.id

    # 4. Conflicting plan_id (pro) and plan_code (basic)
    with pytest.raises(ConflictException) as exc_info:
        svc.resolve_plan(plan_id=pro_plan.id, plan_code="basic")
    assert "resolve to different plans" in str(exc_info.value.detail)


def test_inactive_plan_rejection(db_session: Session):
    """
    Test 4: Inactive plan cannot be selected for subscription.
    """
    inactive_code = f"inactive-{uuid.uuid4().hex[:6]}"
    inactive_plan = SaaSPlan(
        name="Sunset Plan",
        code=inactive_code,
        description="Deprecated plan",
        price=Decimal("1500.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=7,
        is_active=False,
    )
    db_session.add(inactive_plan)
    db_session.commit()
    db_session.refresh(inactive_plan)

    svc = SaaSSubscriptionService(db_session)

    # Rejection by plan_id
    with pytest.raises(AppException) as exc_id:
        svc.resolve_plan(plan_id=inactive_plan.id)
    assert "is inactive" in str(exc_id.value.detail)

    # Rejection by plan_code
    with pytest.raises(AppException) as exc_code:
        svc.resolve_plan(plan_code=inactive_code)
    assert "is inactive" in str(exc_code.value.detail)


# ==============================================================================
# 3. PRICE, BILLING INTERVAL & CURRENCY SNAPSHOT RULES
# ==============================================================================

def test_price_snapshot_rule(db_session: Session):
    """
    Test 5: Create subscription with plan price = 2499.
    Update plan price to 2999.
    Verify existing subscription unit_price remains 2499.
    """
    code = f"snap-price-{uuid.uuid4().hex[:6]}"
    plan = SaaSPlan(
        name="Snapshot Price Plan",
        code=code,
        price=Decimal("2499.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    tenant = Tenant(
        name="Price Snapshot Corp",
        domain=f"domain-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    svc = SaaSSubscriptionService(db_session)
    sub = svc.create_initial_subscription(tenant_id=tenant.id, plan_id=plan.id)
    db_session.commit()
    db_session.refresh(sub)

    assert sub.unit_price == Decimal("2499.00")

    # Catalog update: change price to 2999.00
    plan.price = Decimal("2999.00")
    db_session.commit()

    # Re-query subscription: unit_price must still be 2499.00
    reloaded_sub = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub.id).one()
    assert reloaded_sub.unit_price == Decimal("2499.00")


def test_billing_interval_snapshot_rule(db_session: Session):
    """
    Test 6: Verify subscription retains original billing interval even if plan interval changes.
    """
    code = f"snap-interval-{uuid.uuid4().hex[:6]}"
    plan = SaaSPlan(
        name="Snapshot Interval Plan",
        code=code,
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    tenant = Tenant(
        name="Interval Corp",
        domain=f"domain-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    svc = SaaSSubscriptionService(db_session)
    sub = svc.create_initial_subscription(tenant_id=tenant.id, plan_id=plan.id)
    db_session.commit()
    assert sub.billing_interval == "monthly"

    # Catalog update: change interval to yearly
    plan.billing_interval = "yearly"
    db_session.commit()

    reloaded_sub = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub.id).one()
    assert reloaded_sub.billing_interval == "monthly"


def test_currency_snapshot_rule(db_session: Session):
    """
    Test 7: Verify subscription retains original currency even if plan currency changes.
    """
    code = f"snap-curr-{uuid.uuid4().hex[:6]}"
    plan = SaaSPlan(
        name="Snapshot Currency Plan",
        code=code,
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    tenant = Tenant(
        name="Currency Corp",
        domain=f"domain-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    svc = SaaSSubscriptionService(db_session)
    sub = svc.create_initial_subscription(tenant_id=tenant.id, plan_id=plan.id)
    db_session.commit()
    assert sub.currency == "INR"

    # Catalog update: change currency to USD
    plan.currency = "USD"
    db_session.commit()

    reloaded_sub = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub.id).one()
    assert reloaded_sub.currency == "INR"


# ==============================================================================
# 4. TRIAL DURATION & ZERO-TRIAL BEHAVIOR
# ==============================================================================

def test_dynamic_trial_days_calculation(db_session: Session):
    """
    Test 8: Dynamic trial days calculation (e.g. 7 days, 30 days) from plan configuration.
    """
    svc = SaaSSubscriptionService(db_session)

    for custom_trial in (7, 30):
        code = f"trial-{custom_trial}-{uuid.uuid4().hex[:6]}"
        plan = SaaSPlan(
            name=f"Trial {custom_trial} Plan",
            code=code,
            price=Decimal("500.00"),
            currency="INR",
            billing_interval="monthly",
            trial_days=custom_trial,
            is_active=True,
        )
        db_session.add(plan)
        db_session.commit()

        tenant = Tenant(
            name=f"Trial {custom_trial} Corp",
            domain=f"domain-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        db_session.add(tenant)
        db_session.commit()

        sub = svc.create_initial_subscription(tenant_id=tenant.id, plan_id=plan.id)
        db_session.commit()

        expected_trial_end = sub.start_date + timedelta(days=custom_trial)
        assert sub.status == "trialing"
        assert abs((sub.trial_end_date - expected_trial_end).total_seconds()) < 2
        assert sub.current_period_end == sub.trial_end_date


def test_zero_trial_behavior(db_session: Session):
    """
    Test 9: For plans with trial_days == 0 (e.g. Enterprise):
    - status = active (not trialing)
    - trial_end_date = None
    - current_period_end calculated based on calendar-aware interval (+1 month or +1 year)
    - projection subscription_status = 'active'
    """
    code = f"zero-trial-{uuid.uuid4().hex[:6]}"
    plan = SaaSPlan(
        name="Zero Trial Monthly",
        code=code,
        price=Decimal("4999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=0,
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()

    tenant = Tenant(
        name="Zero Trial Corp",
        domain=f"domain-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    svc = SaaSSubscriptionService(db_session)
    sub = svc.create_initial_subscription(tenant_id=tenant.id, plan_id=plan.id)
    db_session.commit()

    assert sub.status == "active"
    assert sub.trial_end_date is None

    expected_period_end = sub.start_date + relativedelta(months=1)
    assert abs((sub.current_period_end - expected_period_end).total_seconds()) < 2

    # Verify projection
    db_session.refresh(tenant)
    assert tenant.plan == code
    assert tenant.subscription_status == "active"
    assert tenant.subscription_end_date == sub.current_period_end


# ==============================================================================
# 5. PROJECTION SYNCHRONIZATION & MAPPING
# ==============================================================================

def test_projection_synchronization_all_statuses(db_session: Session, ensure_baseline_plans):
    """
    Test 10: Verify sync_tenant_projection correctly synchronizes:
    - tenant.plan
    - tenant.subscription_status
    - tenant.subscription_end_date
    across all defined status mappings.
    """
    basic_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()
    tenant = Tenant(
        name="Projection Test Corp",
        domain=f"domain-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    svc = SaaSSubscriptionService(db_session)
    now = datetime.utcnow()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=basic_plan.id,
        status="trialing",
        billing_interval="monthly",
        unit_price=basic_plan.price,
        currency="INR",
        start_date=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=14),
        trial_end_date=now + timedelta(days=14),
    )
    db_session.add(sub)
    db_session.flush()

    for saas_status, expected_legacy in STATUS_PROJECTION_MAP.items():
        sub.status = saas_status
        svc.sync_tenant_projection(sub)
        db_session.flush()
        db_session.refresh(tenant)

        assert tenant.plan == basic_plan.code
        assert tenant.subscription_status == expected_legacy
        assert tenant.subscription_end_date == sub.current_period_end


# ==============================================================================
# 6. ONE CURRENT SUBSCRIPTION CONCURRENCY RULE
# ==============================================================================

def test_duplicate_current_subscription_rejected(db_session: Session, ensure_baseline_plans):
    """
    Test 11: Attempt to create a second current subscription for a tenant while one is active/trialing/past_due.
    Verify ConflictException (HTTP 409).
    """
    tenant = Tenant(
        name="One Sub Corp",
        domain=f"domain-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    svc = SaaSSubscriptionService(db_session)
    sub1 = svc.create_initial_subscription(tenant_id=tenant.id)
    db_session.commit()
    assert sub1.status in CURRENT_SUBSCRIPTION_STATUSES

    # Attempting to create a second subscription for the same tenant must raise ConflictException
    with pytest.raises(ConflictException) as exc_info:
        svc.create_initial_subscription(tenant_id=tenant.id)

    assert "already has a current subscription" in str(exc_info.value.detail)


# ==============================================================================
# 7. TRANSACTION ATOMICITY & ROLLBACK
# ==============================================================================

def test_registration_transaction_atomicity(db_session: Session):
    """
    Test 12: If subscription creation fails (e.g. inactive plan requested),
    the entire transaction must roll back cleanly.
    Zero partial tenant, user, or subscription records may remain.
    """
    # Create an inactive plan
    code = f"inactive-{uuid.uuid4().hex[:6]}"
    plan = SaaSPlan(
        name="Inactive Atomicity Plan",
        code=code,
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=False,
    )
    db_session.add(plan)
    db_session.commit()

    uid = uuid.uuid4().hex[:8]
    domain = f"atomic-{uid}"
    email = f"owner-{uid}@atomiccorp.com"

    reg_payload = {
        "tenant_name": f"Atomic Corp {uid}",
        "domain": domain,
        "email": email,
        "admin_name": "Atomic Owner",
        "password": "Password123!",
        "phone": "9876543210",
        "plan_code": code,  # Inactive!
    }

    resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code in (400, 422), resp.text

    # Verify complete rollback
    assert db_session.query(Tenant).filter(Tenant.domain == domain).first() is None
    assert db_session.query(User).filter(User.email == email).first() is None
    assert db_session.query(SaaSSubscription).filter(SaaSSubscription.plan_id == plan.id).first() is None


# ==============================================================================
# 8. HISTORICAL BACKFILL INTEGRITY (TASK 1 PRESERVATION)
# ==============================================================================

def test_historical_task1_backfill_integrity(db_session: Session):
    """
    Test 13: Verify that existing backfilled subscriptions from Task 1
    remain unchanged and intact.
    """
    all_subs = db_session.query(SaaSSubscription).all()
    # At least the backfilled baseline exists or is preserved
    for sub in all_subs:
        assert sub.tenant_id is not None
        assert sub.plan_id is not None
        assert sub.unit_price is not None
        assert sub.billing_interval in ("monthly", "yearly")
        assert sub.currency == "INR"
        assert sub.status in ("trialing", "active", "past_due", "cancelled", "expired")


# ==============================================================================
# 9. P2 TASK 6.1 — SUBSCRIPTION LIFECYCLE SERVICE & EXPIRY TRANSITIONS
# ==============================================================================

from app.services.saas_subscription_lifecycle_service import (
    SaaSSubscriptionLifecycleService,
)


def _make_test_tenant(db: Session, prefix: str = "lc") -> Tenant:
    uid = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Tenant {prefix} {uid}",
        domain=f"{prefix}-{uid}.example.com",
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _make_test_sub(
    db: Session,
    tenant: Tenant,
    status: str = "trialing",
    trial_end_date: datetime | None = None,
    current_period_end: datetime | None = None,
    current_period_start: datetime | None = None,
    cancel_at_period_end: bool = False,
    plan_code: str = "basic",
) -> SaaSSubscription:
    plan = db.query(SaaSPlan).filter(SaaSPlan.code == plan_code).first()
    now = datetime.utcnow()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=status,
        billing_interval=plan.billing_interval,
        unit_price=plan.price,
        currency=plan.currency,
        start_date=now - timedelta(days=30),
        current_period_start=current_period_start or (now - timedelta(days=14)),
        current_period_end=current_period_end or (now + timedelta(days=14)),
        trial_end_date=trial_end_date,
        cancel_at_period_end=cancel_at_period_end,
    )
    db.add(sub)
    db.flush()
    SaaSSubscriptionService(db).sync_tenant_projection(sub)
    db.flush()
    return sub


def test_trial_unexpired_remains_trialing(db_session: Session, ensure_baseline_plans):
    """Trial whose trial_end_date is in the future must remain trialing."""
    tenant = _make_test_tenant(db_session, "trial-ok")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="trialing",
        trial_end_date=now + timedelta(days=5),
        current_period_end=now + timedelta(days=5),
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.expire_trials(tenant_id=tenant.id)

    assert count == 0
    db_session.refresh(sub)
    assert sub.status == "trialing"


def test_trial_transitions_to_past_due_at_trial_end(db_session: Session, ensure_baseline_plans):
    """Trial whose trial_end_date <= now transitions directly to past_due (not expired)."""
    tenant = _make_test_tenant(db_session, "trial-exp")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="trialing",
        trial_end_date=now - timedelta(minutes=10),
        current_period_end=now - timedelta(minutes=10),
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.expire_trials(tenant_id=tenant.id)

    assert count == 1
    db_session.refresh(sub)
    db_session.refresh(tenant)
    assert sub.status == "past_due"
    assert tenant.subscription_status == "past_due"


def test_trial_past_due_does_not_expire_before_grace(db_session: Session, ensure_baseline_plans):
    """Trial-originated past_due subscription within 7-day grace period must not expire."""
    tenant = _make_test_tenant(db_session, "trial-grace")
    now = datetime.utcnow()
    # Trial ended 4 days ago (grace is 7 days)
    trial_end = now - timedelta(days=4)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="past_due",
        trial_end_date=trial_end,
        current_period_end=trial_end,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.expire_grace_periods(tenant_id=tenant.id)

    assert count == 0
    db_session.refresh(sub)
    assert sub.status == "past_due"


def test_trial_past_due_expires_at_grace_boundary(db_session: Session, ensure_baseline_plans):
    """Trial-originated past_due subscription whose trial_end_date + grace <= now expires."""
    tenant = _make_test_tenant(db_session, "trial-postgrace")
    now = datetime.utcnow()
    # Trial ended 8 days ago (grace period 7 days expired 1 day ago)
    trial_end = now - timedelta(days=8)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="past_due",
        trial_end_date=trial_end,
        current_period_end=trial_end,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.expire_grace_periods(tenant_id=tenant.id)

    assert count == 1
    db_session.refresh(sub)
    db_session.refresh(tenant)
    assert sub.status == "expired"
    assert tenant.subscription_status == "expired"


def test_active_before_period_end_remains_active(db_session: Session, ensure_baseline_plans):
    """Active subscription whose current_period_end is in the future must remain active."""
    tenant = _make_test_tenant(db_session, "active-ok")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=15),
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.process_period_ends(tenant_id=tenant.id)

    assert count == 0
    db_session.refresh(sub)
    assert sub.status == "active"


def test_active_transitions_to_past_due_at_period_end(db_session: Session, ensure_baseline_plans):
    """Active subscription whose current_period_end <= now and cancel_at_period_end=False transitions to past_due."""
    tenant = _make_test_tenant(db_session, "active-exp")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(hours=2),
        cancel_at_period_end=False,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.process_period_ends(tenant_id=tenant.id)

    assert count == 1
    db_session.refresh(sub)
    db_session.refresh(tenant)
    assert sub.status == "past_due"
    assert tenant.subscription_status == "past_due"


def test_active_cancel_at_period_end_is_not_moved_to_past_due(db_session: Session, ensure_baseline_plans):
    """Active subscription with cancel_at_period_end=True must NOT be moved to past_due."""
    tenant = _make_test_tenant(db_session, "active-cancel")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(hours=2),
        cancel_at_period_end=True,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.process_period_ends(tenant_id=tenant.id)

    assert count == 0
    db_session.refresh(sub)
    assert sub.status == "active"


def test_past_due_remains_past_due_inside_grace(db_session: Session, ensure_baseline_plans):
    """Paid-cycle past_due subscription inside the 7-day grace period must remain past_due."""
    tenant = _make_test_tenant(db_session, "paid-grace")
    now = datetime.utcnow()
    # Paid period ended 3 days ago (grace is 7 days)
    period_end = now - timedelta(days=3)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="past_due",
        trial_end_date=None,
        current_period_end=period_end,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.expire_grace_periods(tenant_id=tenant.id)

    assert count == 0
    db_session.refresh(sub)
    assert sub.status == "past_due"


def test_past_due_transitions_to_expired_at_grace_boundary(db_session: Session, ensure_baseline_plans):
    """Paid-cycle past_due subscription past 7-day grace period transitions to expired."""
    tenant = _make_test_tenant(db_session, "paid-postgrace")
    now = datetime.utcnow()
    # Paid period ended 8 days ago
    period_end = now - timedelta(days=8)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="past_due",
        trial_end_date=None,
        current_period_end=period_end,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.expire_grace_periods(tenant_id=tenant.id)

    assert count == 1
    db_session.refresh(sub)
    db_session.refresh(tenant)
    assert sub.status == "expired"
    assert tenant.subscription_status == "expired"


def test_repeated_lifecycle_execution_is_idempotent(db_session: Session, ensure_baseline_plans):
    """Running lifecycle service repeatedly produces identical state and zero duplicate transitions."""
    # Pre-clean any expired subscriptions left by earlier tests
    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.run_all()

    tenant1 = _make_test_tenant(db_session, "idemp1")
    tenant2 = _make_test_tenant(db_session, "idemp2")
    now = datetime.utcnow()

    # Sub 1: Trial expired
    sub1 = _make_test_sub(
        db_session,
        tenant1,
        status="trialing",
        trial_end_date=now - timedelta(days=1),
        current_period_end=now - timedelta(days=1),
    )
    # Sub 2: Active period expired
    sub2 = _make_test_sub(
        db_session,
        tenant2,
        status="active",
        current_period_end=now - timedelta(days=2),
    )

    # First run: transitions occur
    res1 = svc.run_all()
    assert res1["trials_expired_to_past_due"] == 1
    assert res1["active_subscriptions_moved_to_past_due"] == 1
    assert res1["past_due_subscriptions_expired"] == 0

    db_session.refresh(sub1)
    db_session.refresh(sub2)
    assert sub1.status == "past_due"
    assert sub2.status == "past_due"

    # Second run immediately after: exact same state, 0 transitions
    res2 = svc.run_all()
    assert res2["trials_expired_to_past_due"] == 0
    assert res2["active_subscriptions_moved_to_past_due"] == 0
    assert res2["past_due_subscriptions_expired"] == 0

    db_session.refresh(sub1)
    db_session.refresh(sub2)
    assert sub1.status == "past_due"
    assert sub2.status == "past_due"


def test_lifecycle_transition_syncs_tenant_projection(db_session: Session, ensure_baseline_plans):
    """Lifecycle transitions synchronize tenant projection fields in real-time."""
    tenant = _make_test_tenant(db_session, "proj-sync")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(minutes=30),
    )
    db_session.refresh(tenant)
    assert tenant.subscription_status == "active"

    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.process_period_ends(tenant_id=tenant.id)

    db_session.refresh(tenant)
    assert tenant.subscription_status == "past_due"
    assert tenant.subscription_end_date == sub.current_period_end


def test_future_dated_historical_subscriptions_are_untouched(db_session: Session, ensure_baseline_plans):
    """Future-dated subscriptions in the system remain untouched during lifecycle processing."""
    now = datetime.utcnow()
    future_subs = (
        db_session.query(SaaSSubscription)
        .filter(
            SaaSSubscription.current_period_end > now,
            SaaSSubscription.status.in_(["trialing", "active"]),
        )
        .all()
    )
    statuses_before = {s.id: s.status for s in future_subs}

    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.run_all()

    for sub_id, old_status in statuses_before.items():
        refreshed = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).first()
        assert refreshed.status == old_status


def test_concurrent_lifecycle_processing_threads(db_session: Session, ensure_baseline_plans):
    """
    Two concurrent worker threads attempting to transition the exact same subscription
    execute safely without race conditions. Exactly one worker performs the transition.
    """
    import concurrent.futures
    tenant = _make_test_tenant(db_session, "concur-worker")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(hours=1),
    )
    sub_id = sub.id
    db_session.commit()

    results = []

    def worker():
        worker_db = SessionLocal()
        try:
            svc = SaaSSubscriptionLifecycleService(worker_db)
            count = svc.process_period_ends(tenant_id=tenant.id)
            worker_db.commit()
            results.append(count)
        finally:
            worker_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        f1.result()
        f2.result()

    # Exactly one worker transitioned the subscription, the other was a safe no-op
    assert sum(results) == 1, f"Expected total 1 transition, got {results}"

    db_session.refresh(sub)
    assert sub.status == "past_due"


# ==============================================================================
# TASK 6.2 HELPERS & TESTS
# ==============================================================================

def _make_test_user(db: Session, tenant: Tenant) -> tuple[User, dict]:
    uid = uuid.uuid4().hex[:8]
    role = Role(
        tenant_id=tenant.id,
        name=f"admin_{uid}",
        permissions=["*"],
        is_system=True,
    )
    db.add(role)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        role_id=role.id,
        email=f"user_{uid}@example.com",
        full_name=f"Test User {uid}",
        password_hash="hashed_dummy_password",
        is_active=True,
    )
    db.add(user)
    db.flush()
    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": tenant.id,
        "email": user.email,
        "role": role.name,
    })
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


def _make_test_super_admin(db: Session) -> tuple[SuperAdmin, dict]:
    uid = uuid.uuid4().hex[:8]
    sa = SuperAdmin(
        email=f"sa_{uid}@example.com",
        full_name=f"SA {uid}",
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
# 1. CANCELLATION TESTS
# ------------------------------------------------------------------------------

def test_active_cancellation_sets_cancel_at_period_end_and_timestamp(db_session: Session, ensure_baseline_plans):
    """Normal cancellation sets cancel_at_period_end=True, populates cancelled_at, and keeps status=active."""
    tenant = _make_test_tenant(db_session, "cancel-norm")
    sub = _make_test_sub(db_session, tenant, status="active")

    svc = SaaSSubscriptionService(db_session)
    res = svc.cancel_subscription(tenant.id)

    assert res.cancel_at_period_end is True
    assert res.cancelled_at is not None
    assert res.status == "active"
    db_session.refresh(tenant)
    assert tenant.subscription_status == "active"


def test_cancellation_is_idempotent(db_session: Session, ensure_baseline_plans):
    """Repeated cancellation calls return existing state without corrupting or duplicating."""
    tenant = _make_test_tenant(db_session, "cancel-idemp")
    sub = _make_test_sub(db_session, tenant, status="active")

    svc = SaaSSubscriptionService(db_session)
    r1 = svc.cancel_subscription(tenant.id)
    first_cancelled_at = r1.cancelled_at
    assert r1.cancel_at_period_end is True

    r2 = svc.cancel_subscription(tenant.id)
    assert r2.cancel_at_period_end is True
    assert r2.cancelled_at == first_cancelled_at
    assert r2.status == "active"


def test_terminal_subscriptions_cannot_be_cancelled(db_session: Session, ensure_baseline_plans):
    """Cancelled or expired subscriptions reject subsequent cancellation requests."""
    t1 = _make_test_tenant(db_session, "term-canc")
    _make_test_sub(db_session, t1, status="cancelled")
    svc = SaaSSubscriptionService(db_session)
    with pytest.raises(AppException) as exc1:
        svc.cancel_subscription(t1.id)
    assert "already 'cancelled'" in str(exc1.value.detail)

    t2 = _make_test_tenant(db_session, "term-exp")
    _make_test_sub(db_session, t2, status="expired")
    with pytest.raises(AppException) as exc2:
        svc.cancel_subscription(t2.id)
    assert "already 'expired'" in str(exc2.value.detail)


def test_tenant_cancellation_api_success_and_isolation(db_session: Session, ensure_baseline_plans):
    """Tenant can cancel own subscription via API; anonymous requests are rejected."""
    tenant = _make_test_tenant(db_session, "api-cancel")
    _make_test_sub(db_session, tenant, status="active")
    user, headers = _make_test_user(db_session, tenant)
    db_session.commit()

    # Successful tenant-owned cancellation
    resp = client.post(
        "/api/v1/saas-billing/subscription/cancel",
        json={"cancel_at_period_end": True, "reason": "Moving off platform"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cancel_at_period_end"] is True
    assert data["cancelled_at"] is not None
    assert data["status"] == "active"

    # Anonymous request rejected
    resp_anon = client.post(
        "/api/v1/saas-billing/subscription/cancel",
        json={"cancel_at_period_end": True},
    )
    assert resp_anon.status_code == 401


# ------------------------------------------------------------------------------
# 2. SCHEDULED CANCELLATION LIFECYCLE TESTS
# ------------------------------------------------------------------------------

def test_scheduled_cancellation_remains_active_before_period_end(db_session: Session, ensure_baseline_plans):
    """Subscription marked cancel_at_period_end remains active prior to current_period_end."""
    tenant = _make_test_tenant(db_session, "sched-canc-pre")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=3),
        cancel_at_period_end=True,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.process_scheduled_cancellations(tenant_id=tenant.id)
    assert count == 0
    db_session.refresh(sub)
    assert sub.status == "active"


def test_scheduled_cancellation_transitions_to_cancelled_at_period_end(db_session: Session, ensure_baseline_plans):
    """Subscription marked cancel_at_period_end transitions to cancelled when current_period_end <= now."""
    tenant = _make_test_tenant(db_session, "sched-canc-post")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(hours=1),
        cancel_at_period_end=True,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.process_scheduled_cancellations(tenant_id=tenant.id)
    assert count == 1
    db_session.refresh(sub)
    db_session.refresh(tenant)
    assert sub.status == "cancelled"
    assert tenant.subscription_status == "cancelled"


def test_scheduled_cancellation_never_becomes_past_due(db_session: Session, ensure_baseline_plans):
    """CRITICAL: Scheduled cancellation transitions directly to cancelled and is never moved to past_due."""
    tenant = _make_test_tenant(db_session, "never-pastdue")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(hours=2),
        cancel_at_period_end=True,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    summary = svc.run_all(tenant_id=tenant.id)

    assert summary["scheduled_cancellations_processed"] == 1
    assert summary["active_subscriptions_moved_to_past_due"] == 0
    db_session.refresh(sub)
    assert sub.status == "cancelled"


def test_concurrent_scheduled_cancellations_threads(db_session: Session, ensure_baseline_plans):
    """Two concurrent threads processing scheduled cancellations transition the record exactly once."""
    import concurrent.futures
    tenant = _make_test_tenant(db_session, "concur-canc")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now - timedelta(hours=1),
        cancel_at_period_end=True,
    )
    sub_id = sub.id
    tenant_id = tenant.id
    db_session.commit()

    results = []

    def worker():
        worker_db = SessionLocal()
        try:
            svc = SaaSSubscriptionLifecycleService(worker_db)
            cnt = svc.process_scheduled_cancellations(tenant_id=tenant_id)
            worker_db.commit()
            results.append(cnt)
        finally:
            worker_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        f1.result()
        f2.result()

    assert sum(results) == 1, f"Expected exactly 1 transition, got {results}"
    db_session.refresh(sub)
    assert sub.status == "cancelled"


# ------------------------------------------------------------------------------
# 3. RENEWAL INVOICE GENERATION TESTS
# ------------------------------------------------------------------------------

def test_renewal_invoice_inside_and_outside_advance_window(db_session: Session, ensure_baseline_plans):
    """Renewal invoice is generated inside the 7-day advance window, but not outside it."""
    now = datetime.utcnow()
    t_inside = _make_test_tenant(db_session, "inv-inside")
    sub_inside = _make_test_sub(
        db_session,
        t_inside,
        status="active",
        current_period_end=now + timedelta(days=5),
        cancel_at_period_end=False,
    )

    t_outside = _make_test_tenant(db_session, "inv-outside")
    sub_outside = _make_test_sub(
        db_session,
        t_outside,
        status="active",
        current_period_end=now + timedelta(days=12),
        cancel_at_period_end=False,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count_inside = svc.generate_upcoming_renewal_invoices(tenant_id=t_inside.id)
    count_outside = svc.generate_upcoming_renewal_invoices(tenant_id=t_outside.id)

    assert count_inside == 1
    assert count_outside == 0

    inv = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub_inside.id)
        .first()
    )
    assert inv is not None
    assert inv.billing_reason == "subscription_cycle"
    assert inv.due_date == sub_inside.current_period_end


def test_renewal_invoice_at_exact_boundary(db_session: Session, ensure_baseline_plans):
    """Renewal invoice is generated at the exact 7-day advance boundary."""
    now = datetime.utcnow()
    tenant = _make_test_tenant(db_session, "inv-boundary")
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=7),
        cancel_at_period_end=False,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    assert count == 1


def test_past_due_generates_renewal_invoice_if_missing(db_session: Session, ensure_baseline_plans):
    """A past_due subscription within grace generates a renewal invoice if one does not exist."""
    now = datetime.utcnow()
    tenant = _make_test_tenant(db_session, "inv-pastdue")
    sub = _make_test_sub(
        db_session,
        tenant,
        status="past_due",
        current_period_end=now - timedelta(days=2),
        cancel_at_period_end=False,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    count = svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    assert count == 1


def test_cancel_at_period_end_and_terminal_generate_no_renewal_invoice(db_session: Session, ensure_baseline_plans):
    """Subscriptions scheduled for cancellation or in terminal states generate zero renewal invoices."""
    now = datetime.utcnow()
    t_cancel = _make_test_tenant(db_session, "inv-cancel")
    _make_test_sub(
        db_session,
        t_cancel,
        status="active",
        current_period_end=now + timedelta(days=3),
        cancel_at_period_end=True,
    )

    t_term = _make_test_tenant(db_session, "inv-term")
    _make_test_sub(
        db_session,
        t_term,
        status="cancelled",
        current_period_end=now - timedelta(days=3),
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    assert svc.generate_upcoming_renewal_invoices(tenant_id=t_cancel.id) == 0
    assert svc.generate_upcoming_renewal_invoices(tenant_id=t_term.id) == 0


def test_renewal_invoice_snapshot_price_currency_and_due_date(db_session: Session, ensure_baseline_plans):
    """Renewal invoice preserves snapshot price and currency from subscription, ignoring catalog updates."""
    tenant = _make_test_tenant(db_session, "inv-snap")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=2),
        plan_code="basic",
    )
    # Mutate the catalog price in SaaSPlan
    plan = db_session.query(SaaSPlan).filter(SaaSPlan.id == sub.plan_id).first()
    original_catalog_price = plan.price
    plan.price = Decimal("9999.00")
    db_session.flush()

    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)

    inv = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .first()
    )
    assert inv is not None
    assert inv.subtotal == sub.unit_price  # Snapshot price, NOT 9999.00!
    assert inv.currency == sub.currency
    assert inv.due_date == sub.current_period_end
    assert inv.billing_reason == "subscription_cycle"

    # Restore plan catalog price
    plan.price = original_catalog_price
    db_session.flush()


def test_repeated_invoice_generation_is_idempotent(db_session: Session, ensure_baseline_plans):
    """Running invoice generation multiple times does not produce duplicate invoices for the same cycle."""
    tenant = _make_test_tenant(db_session, "inv-idemp")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=4),
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    c1 = svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    c2 = svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)

    assert c1 == 1
    assert c2 == 0
    invoices = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .all()
    )
    assert len(invoices) == 1


def test_paid_cycle_invoice_prevents_duplicate_invoice_generation(db_session: Session, ensure_baseline_plans):
    """An existing PAID invoice for the billing cycle prevents generating another invoice for that cycle."""
    tenant = _make_test_tenant(db_session, "inv-paid-prev")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=3),
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)

    inv = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .first()
    )
    inv.status = "paid"
    inv.paid_at = now
    db_session.flush()

    # Second lifecycle run
    c2 = svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    assert c2 == 0
    invoices = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .all()
    )
    assert len(invoices) == 1
    assert invoices[0].status == "paid"


def test_concurrent_renewal_invoice_generation_threads(db_session: Session, ensure_baseline_plans):
    """Two concurrent threads executing renewal invoice generation produce exactly 1 invoice."""
    import concurrent.futures
    tenant = _make_test_tenant(db_session, "concur-inv")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=now + timedelta(days=3),
    )
    sub_id = sub.id
    tenant_id = tenant.id
    db_session.commit()

    results = []

    def worker():
        worker_db = SessionLocal()
        try:
            svc = SaaSSubscriptionLifecycleService(worker_db)
            cnt = svc.generate_upcoming_renewal_invoices(tenant_id=tenant_id)
            worker_db.commit()
            results.append(cnt)
        finally:
            worker_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        f1.result()
        f2.result()

    assert sum(results) == 1, f"Expected exactly 1 invoice generated, got {results}"
    invoices = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub_id)
        .all()
    )
    assert len(invoices) == 1


# ------------------------------------------------------------------------------
# 4. RENEWAL PAYMENT VERIFICATION & PERIOD ADVANCEMENT TESTS
# ------------------------------------------------------------------------------

def test_active_renewal_payment_verification_advances_period(db_session: Session, ensure_baseline_plans):
    """Verifying payment for a renewal invoice advances current_period_end by 1 month from old current_period_end."""
    tenant = _make_test_tenant(db_session, "pay-active")
    now = datetime.utcnow()
    old_end = now + timedelta(days=2)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=old_end,
    )

    # 1. Generate renewal invoice
    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    inv = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .first()
    )
    assert inv.status == "unpaid"

    # 2. Checkout & submit UTR
    upi_svc = SaaSUPIService(db_session)
    init = upi_svc.initiate_checkout(tenant.id, inv.id)
    ref = init["reference"]
    upi_svc.submit_utr(tenant.id, ref, "UTR-ACTIVE-REN-12345", "payer@upi", None)

    # 3. Super Admin verifies
    sa, _ = _make_test_super_admin(db_session)
    upi_svc.verify_transaction(ref, sa.id)

    db_session.refresh(sub)
    db_session.refresh(tenant)
    db_session.refresh(inv)

    assert inv.status == "paid"
    assert sub.status == "active"
    assert sub.current_period_start == old_end
    assert sub.current_period_end == old_end + relativedelta(months=1)
    assert tenant.subscription_status == "active"
    assert tenant.subscription_end_date == sub.current_period_end


def test_past_due_renewal_payment_verification_advances_period_and_restores_active(db_session: Session, ensure_baseline_plans):
    """Payment during grace period restores active status and advances from old period end (never starts from now)."""
    tenant = _make_test_tenant(db_session, "pay-pastdue")
    now = datetime.utcnow()
    # Expired 3 days ago (in grace period)
    old_end = now - timedelta(days=3)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="past_due",
        current_period_end=old_end,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    inv = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .first()
    )

    upi_svc = SaaSUPIService(db_session)
    init = upi_svc.initiate_checkout(tenant.id, inv.id)
    ref = init["reference"]
    upi_svc.submit_utr(tenant.id, ref, "UTR-PASTDUE-REN-67890", "payer@upi", None)

    sa, _ = _make_test_super_admin(db_session)
    upi_svc.verify_transaction(ref, sa.id)

    db_session.refresh(sub)
    db_session.refresh(tenant)

    # Continuous anchor verification: MUST NOT start from now!
    assert sub.status == "active"
    assert sub.current_period_start == old_end
    assert sub.current_period_end == old_end + relativedelta(months=1)
    assert tenant.subscription_status == "active"


def test_yearly_renewal_payment_advances_by_one_year(db_session: Session, ensure_baseline_plans):
    """Yearly subscriptions advance current_period_end by exactly 1 calendar year using relativedelta."""
    # Create yearly plan
    yearly_code = f"yearly-{uuid.uuid4().hex[:6]}"
    yearly_plan = SaaSPlan(
        name="Yearly Plan",
        code=yearly_code,
        price=Decimal("9999.00"),
        currency="INR",
        billing_interval="yearly",
        trial_days=0,
        is_active=True,
    )
    db_session.add(yearly_plan)
    db_session.flush()

    tenant = _make_test_tenant(db_session, "pay-yearly")
    now = datetime.utcnow()
    old_end = now + timedelta(days=2)
    sub = _make_test_sub(
        db_session,
        tenant,
        status="active",
        current_period_end=old_end,
        plan_code=yearly_code,
    )

    svc = SaaSSubscriptionLifecycleService(db_session)
    svc.generate_upcoming_renewal_invoices(tenant_id=tenant.id)
    inv = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id == sub.id)
        .first()
    )

    upi_svc = SaaSUPIService(db_session)
    init = upi_svc.initiate_checkout(tenant.id, inv.id)
    ref = init["reference"]
    upi_svc.submit_utr(tenant.id, ref, "UTR-YEARLY-123", "payer@upi", None)

    sa, _ = _make_test_super_admin(db_session)
    upi_svc.verify_transaction(ref, sa.id)

    db_session.refresh(sub)
    assert sub.current_period_start == old_end
    assert sub.current_period_end == old_end + relativedelta(years=1)


def test_terminal_subscription_renewal_payment_rejected(db_session: Session, ensure_baseline_plans):
    """Payment verification for a cancelled or expired subscription is rejected with AppException."""
    tenant = _make_test_tenant(db_session, "pay-term")
    now = datetime.utcnow()
    sub = _make_test_sub(
        db_session,
        tenant,
        status="cancelled",
        current_period_end=now - timedelta(days=5),
    )

    inv_svc = SaaSInvoiceService(db_session)
    # Manually create invoice referencing this subscription
    inv = SaaSInvoice(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_number=f"INV-TEST-{uuid.uuid4().hex[:6]}",
        billing_reason="subscription_cycle",
        subtotal=sub.unit_price,
        tax_amount=Decimal("0.00"),
        total_amount=sub.unit_price,
        currency="INR",
        status="unpaid",
        due_date=sub.current_period_end,
    )
    db_session.add(inv)
    db_session.flush()

    upi_svc = SaaSUPIService(db_session)
    init = upi_svc.initiate_checkout(tenant.id, inv.id)
    ref = init["reference"]
    upi_svc.submit_utr(tenant.id, ref, "UTR-TERM-FAIL", "payer@upi", None)

    sa, _ = _make_test_super_admin(db_session)
    with pytest.raises(AppException) as exc:
        upi_svc.verify_transaction(ref, sa.id)
    assert "Terminal subscriptions cannot be reactivated" in str(exc.value.detail)


# ------------------------------------------------------------------------------
# 5. SUPER ADMIN LIFECYCLE ENDPOINT & CLI TESTS
# ------------------------------------------------------------------------------

def test_super_admin_subscription_lifecycle_endpoint(db_session: Session, ensure_baseline_plans):
    """Super Admin can trigger subscription lifecycle processing via operational endpoint."""
    sa, headers = _make_test_super_admin(db_session)
    db_session.commit()

    resp = client.post(
        "/api/v1/super-admins/subscription-lifecycle/process",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "trials_expired_to_past_due" in data
    assert "scheduled_cancellations_processed" in data
    assert "active_subscriptions_moved_to_past_due" in data
    assert "past_due_subscriptions_expired" in data
    assert "renewal_invoices_generated" in data


def test_tenant_cannot_access_super_admin_lifecycle_endpoint(db_session: Session, ensure_baseline_plans):
    """Tenant token cannot access the Super Admin operational lifecycle endpoint."""
    tenant = _make_test_tenant(db_session, "tenant-no-sa")
    user, headers = _make_test_user(db_session, tenant)
    db_session.commit()

    resp = client.post(
        "/api/v1/super-admins/subscription-lifecycle/process",
        headers=headers,
    )
    assert resp.status_code in (401, 403)


def test_cli_runner_success_and_failure(db_session: Session, ensure_baseline_plans):
    """CLI runner executes cleanly returning 0 on success and 1 on unhandled exception."""
    # 1. Success execution
    code = cli_lifecycle_main()
    assert code == 0

    # 2. Failure execution
    with patch.object(SaaSSubscriptionLifecycleService, "run_all", side_effect=RuntimeError("Simulated DB failure")):
        fail_code = cli_lifecycle_main()
        assert fail_code == 1

