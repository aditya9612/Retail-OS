import os
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.saas_billing import (
    SaaSPlan,
    SaaSSubscription,
    SaaSInvoice,
    SaaSUPITransaction,
)
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def ensure_baseline_plans(db_session):
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
# 1. PLAN CATALOG & SEED VERIFICATION TESTS
# ==============================================================================

def test_initial_plan_catalog_seed(db_session):
    """Verify that baseline plans exist with correct attributes."""
    plans = db_session.query(SaaSPlan).all()
    assert len(plans) >= 3

    plan_codes = {p.code: p for p in plans}
    assert "basic" in plan_codes
    assert "pro" in plan_codes
    assert "enterprise" in plan_codes

    # 1. Basic Plan
    basic = plan_codes["basic"]
    assert basic.name == "Basic"
    assert basic.price == Decimal("999.00")
    assert basic.billing_interval == "monthly"
    assert basic.trial_days == 14
    assert basic.is_active is True
    assert basic.currency == "INR"

    # 2. Pro Plan
    pro = plan_codes["pro"]
    assert pro.name == "Pro"
    assert pro.price == Decimal("2499.00")
    assert pro.billing_interval == "monthly"
    assert pro.trial_days == 14
    assert pro.is_active is True
    assert pro.currency == "INR"

    # 3. Enterprise Plan
    enterprise = plan_codes["enterprise"]
    assert enterprise.name == "Enterprise"
    assert enterprise.price == Decimal("4999.00")
    assert enterprise.billing_interval == "monthly"
    assert enterprise.trial_days == 0
    assert enterprise.is_active is True
    assert enterprise.currency == "INR"


def test_saas_plan_unique_code_constraint(db_session):
    """Verify that duplicate plan code is rejected by database UNIQUE constraint."""
    dup_plan = SaaSPlan(
        name="Duplicate Basic",
        code="basic",  # already exists
        price=Decimal("1299.00"),
        billing_interval="monthly",
        trial_days=7,
        is_active=True,
    )
    db_session.add(dup_plan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_saas_plan_active_flag_and_crud_suitability(db_session):
    """Verify that SaaS plans are database-editable and can be deactivated without deletion."""
    test_code = f"custom_{uuid.uuid4().hex[:6]}"
    new_plan = SaaSPlan(
        name="Custom Retail Plan",
        code=test_code,
        description="Editable plan for custom retail chains.",
        price=Decimal("3499.00"),
        billing_interval="monthly",
        trial_days=21,
        is_active=True,
    )
    db_session.add(new_plan)
    db_session.commit()

    # Verify created
    saved = db_session.query(SaaSPlan).filter(SaaSPlan.code == test_code).first()
    assert saved is not None
    assert saved.price == Decimal("3499.00")

    # Update pricing & deactivation (simulating future CRUD action)
    saved.price = Decimal("3999.00")
    saved.is_active = False
    db_session.commit()

    refetched = db_session.query(SaaSPlan).filter(SaaSPlan.code == test_code).first()
    assert refetched.price == Decimal("3999.00")
    assert refetched.is_active is False


# ==============================================================================
# 2. MODEL RELATIONSHIPS & CONSTRAINTS TESTS
# ==============================================================================

def test_saas_subscription_pricing_snapshot_rule(db_session):
    """Verify that subscription locks in unit_price snapshot independently of catalog plan changes."""
    basic_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()

    tenant = Tenant(
        name="Snapshot Test Tenant",
        domain=f"snapshot-{uuid.uuid4().hex[:6]}",
        is_active=True,
        plan="basic",
        subscription_status="trial",
    )
    db_session.add(tenant)
    db_session.flush()

    # Create subscription snapping current plan price
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=basic_plan.id,
        status="active",
        billing_interval="monthly",
        unit_price=basic_plan.price,  # snapshot: 999.00
        currency="INR",
        start_date=datetime.utcnow(),
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.commit()

    assert sub.unit_price == Decimal("999.00")

    # Super Admin updates catalog price of Basic plan to 1199.00
    original_price = basic_plan.price
    basic_plan.price = Decimal("1199.00")
    db_session.commit()

    # Re-fetch subscription and verify its unit_price remains at agreed snapshot 999.00
    refetched_sub = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub.id).first()
    assert refetched_sub.unit_price == Decimal("999.00")
    assert basic_plan.price == Decimal("1199.00")

    # Restore basic plan price for clean state
    basic_plan.price = original_price
    db_session.commit()


def test_saas_invoice_unique_number_and_relationships(db_session):
    """Verify SaaSInvoice creation, relationships, and unique invoice_number constraint."""
    tenant = Tenant(
        name="Invoice Test Tenant",
        domain=f"inv-{uuid.uuid4().hex[:6]}",
        is_active=True,
        plan="basic",
        subscription_status="trial",
    )
    db_session.add(tenant)
    db_session.flush()

    basic_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=basic_plan.id,
        status="trialing",
        billing_interval="monthly",
        unit_price=Decimal("0.00"),
        currency="INR",
        start_date=datetime.utcnow(),
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(sub)
    db_session.flush()

    inv_num = f"INV-SAAS-{uuid.uuid4().hex[:8].upper()}"
    inv = SaaSInvoice(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_number=inv_num,
        billing_reason="subscription_cycle",
        subtotal=Decimal("999.00"),
        tax_amount=Decimal("179.82"),
        total_amount=Decimal("1178.82"),
        currency="INR",
        status="unpaid",
        due_date=datetime.utcnow() + timedelta(days=7),
    )
    db_session.add(inv)
    db_session.commit()

    assert inv.id is not None
    assert inv.subscription.id == sub.id
    assert inv.tenant.id == tenant.id

    # Test duplicate invoice_number rejection
    dup_inv = SaaSInvoice(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_number=inv_num,
        billing_reason="subscription_cycle",
        subtotal=Decimal("999.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("999.00"),
        currency="INR",
        status="unpaid",
        due_date=datetime.utcnow() + timedelta(days=7),
    )
    db_session.add(dup_inv)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_saas_upi_transaction_lifecycle_and_constraints(db_session):
    """Verify SaaSUPITransaction creation, unique reference, nullable UTR, and Super Admin FK."""
    tenant = Tenant(
        name="UPI Test Tenant",
        domain=f"upi-{uuid.uuid4().hex[:6]}",
        is_active=True,
        plan="pro",
        subscription_status="active",
    )
    db_session.add(tenant)
    db_session.flush()

    pro_plan = db_session.query(SaaSPlan).filter(SaaSPlan.code == "pro").first()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=pro_plan.id,
        status="active",
        billing_interval="monthly",
        unit_price=Decimal("2499.00"),
        currency="INR",
        start_date=datetime.utcnow(),
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db_session.add(sub)
    db_session.flush()

    inv_num = f"INV-SAAS-{uuid.uuid4().hex[:8].upper()}"
    inv = SaaSInvoice(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_number=inv_num,
        billing_reason="subscription_cycle",
        subtotal=Decimal("2499.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("2499.00"),
        currency="INR",
        status="unpaid",
        due_date=datetime.utcnow() + timedelta(days=7),
    )
    db_session.add(inv)
    db_session.flush()

    ref1 = f"TXN_UPI_{uuid.uuid4().hex}"
    txn = SaaSUPITransaction(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_id=inv.id,
        reference=ref1,
        utr=None,  # Pending checkout has no UTR yet
        amount=inv.total_amount,
        currency="INR",
        status="pending",
        upi_id="retailos@icici",
        payer_vpa=None,
        proof_image_url=None,
    )
    db_session.add(txn)
    db_session.commit()

    assert txn.id is not None
    assert txn.utr is None
    assert txn.status == "pending"

    # Test duplicate reference rejection
    dup_txn = SaaSUPITransaction(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_id=inv.id,
        reference=ref1,  # Duplicate reference
        amount=inv.total_amount,
        currency="INR",
        status="pending",
        upi_id="retailos@icici",
    )
    db_session.add(dup_txn)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ==============================================================================
# 3. LIVE MYSQL REPOSITORY BACKFILL & PROJECTION VERIFICATION
# ==============================================================================

def test_live_mysql_migration_and_backfill_state():
    """Verify live MySQL 8 state for the 3 seeded plans, 13 backfilled subscriptions, and projections."""
    from dotenv import dotenv_values
    env = dotenv_values(".env")
    mysql_url = env.get("DATABASE_URL")
    if not mysql_url or "mysql" not in mysql_url.lower():
        pytest.skip("Not configured with live MySQL DATABASE_URL in .env")

    engine = create_engine(mysql_url)
    with engine.connect() as conn:
        # 1. Verify table counts
        plans_count = conn.execute(text("SELECT COUNT(*) FROM saas_plans")).scalar()
        assert plans_count == 3

        subs_count = conn.execute(text("SELECT COUNT(*) FROM saas_subscriptions")).scalar()
        assert subs_count == 13

        invoices_count = conn.execute(text("SELECT COUNT(*) FROM saas_invoices")).scalar()
        assert invoices_count == 0

        upi_count = conn.execute(text("SELECT COUNT(*) FROM saas_upi_transactions")).scalar()
        assert upi_count == 0

        # 2. Verify subscription statuses: 8 trialing, 5 active
        trialing_count = conn.execute(
            text("SELECT COUNT(*) FROM saas_subscriptions WHERE status = 'trialing'")
        ).scalar()
        assert trialing_count == 8

        active_count = conn.execute(
            text("SELECT COUNT(*) FROM saas_subscriptions WHERE status = 'active'")
        ).scalar()
        assert active_count == 5

        # 3. Verify tenant projection synchronization: all 13 have subscription_end_date populated
        null_dates = conn.execute(
            text("SELECT COUNT(*) FROM tenants WHERE subscription_end_date IS NULL")
        ).scalar()
        assert null_dates == 0

        # 4. Verify each tenant's subscription_end_date == subscription.current_period_end
        joined = conn.execute(
            text(
                "SELECT t.id, t.subscription_end_date, s.current_period_end "
                "FROM tenants t "
                "JOIN saas_subscriptions s ON t.id = s.tenant_id"
            )
        ).fetchall()
        assert len(joined) == 13
        for row in joined:
            assert row[1] == row[2]
