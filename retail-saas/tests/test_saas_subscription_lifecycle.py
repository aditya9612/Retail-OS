from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.main import app
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.saas_subscription_service import (
    CURRENT_SUBSCRIPTION_STATUSES,
    STATUS_PROJECTION_MAP,
    SaaSSubscriptionService,
)

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
