from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import (
    create_access_token,
    create_super_admin_access_token,
    get_password_hash,
)
from app.main import app
from app.models.saas_billing import SaaSInvoice, SaaSPlan, SaaSSubscription, SaaSUPITransaction
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.store import Store
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.services.saas_subscription_lifecycle_service import SaaSSubscriptionLifecycleService
from app.services.saas_upi_service import SaaSUPIService

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_test_tenant(prefix: str):
    clean = "".join([c for c in prefix if c.isalnum()]).lower() or "t"
    uid = uuid.uuid4().hex[:6]
    email = f"{clean}{uid}@example.com"
    password = "Password123!"
    phone = f"91{uuid.uuid4().int % 100000000:08d}"

    reg_payload = {
        "tenant_name": f"{clean} Tenant {uid}",
        "domain": f"{clean}-{uid}",
        "email": email,
        "admin_name": f"Admin {uid}",
        "password": password,
        "phone": phone,
    }
    r = client.post("/api/v1/auth/register", json=reg_payload)
    assert r.status_code == 200, f"Registration failed: {r.text}"
    tenant_id = r.json()["tenant_id"]

    login_r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_r.status_code == 200, f"Login failed: {login_r.text}"
    token = login_r.json()["access_token"]

    return {
        "tenant_id": tenant_id,
        "token": token,
        "email": email,
        "user_id": login_r.json().get("user_id"),
    }


@pytest.fixture
def active_super_admin(db: Session):
    uid = uuid.uuid4().hex[:6]
    admin = SuperAdmin(
        email=f"admin_{uid}@example.com",
        full_name=f"Admin {uid}",
        hashed_password=get_password_hash("AdminPass123!"),
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    token = create_super_admin_access_token({
        "sub": str(admin.id),
        "email": admin.email,
        "role": "SUPERADMIN",
    })
    return {
        "admin": admin,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_plan_change_authorization():
    # 1. Anonymous rejected
    r = client.get("/api/v1/saas-billing/subscription")
    assert r.status_code == 401

    r = client.post("/api/v1/saas-billing/subscription/change", json={"target_plan_id": 2})
    assert r.status_code == 401

    # 2. Super admin cannot use tenant route (no tenant_id)
    admin_token = create_super_admin_access_token({"sub": "999", "role": "SUPERADMIN"})
    r = client.get(
        "/api/v1/saas-billing/subscription",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (401, 403)


def test_list_active_plans(db: Session):
    t_data = create_test_tenant("listplans")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    r = client.get("/api/v1/saas-billing/plans", headers=headers)
    assert r.status_code == 200
    plans = r.json()
    assert isinstance(plans, list)
    assert len(plans) >= 2
    # Verify sorted by price
    prices = [Decimal(str(p["price"])) for p in plans]
    assert prices == sorted(prices)


def test_same_plan_request_rejected(db: Session):
    t_data = create_test_tenant("sameplan")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    # Get current plan
    sub_r = client.get("/api/v1/saas-billing/subscription", headers=headers)
    assert sub_r.status_code == 200
    curr_plan_id = sub_r.json()["plan_id"]

    # Request change to the same plan
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": curr_plan_id},
        headers=headers,
    )
    assert r.status_code == 400
    assert "already on plan" in r.json()["detail"]["message"].lower()


def test_target_plan_validation(db: Session):
    t_data = create_test_tenant("planval")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    # Non-existent target plan
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": 999999},
        headers=headers,
    )
    assert r.status_code == 404

    # Inactive target plan
    inactive = SaaSPlan(
        name="Inactive Legacy",
        code=f"inact_{uuid.uuid4().hex[:6]}",
        price=Decimal("1500.00"),
        is_active=False,
    )
    db.add(inactive)
    db.commit()
    db.refresh(inactive)

    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": inactive.id},
        headers=headers,
    )
    assert r.status_code == 400
    assert "inactive" in r.json()["detail"]["message"].lower()


def test_upgrade_flow_and_payment_verification(db: Session, active_super_admin):
    t_data = create_test_tenant("upgflow")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    # Create low and high plans
    low_plan = SaaSPlan(
        name="Starter Tier",
        code=f"starter_{uuid.uuid4().hex[:6]}",
        price=Decimal("500.00"),
        currency="INR",
        is_active=True,
    )
    high_plan = SaaSPlan(
        name="Growth Tier",
        code=f"growth_{uuid.uuid4().hex[:6]}",
        price=Decimal("2000.00"),
        currency="INR",
        is_active=True,
    )
    db.add_all([low_plan, high_plan])
    db.commit()

    # Set starter entitlements (2 stores) and growth entitlements (10 stores)
    db.add_all([
        SaaSPlanEntitlement(plan_id=low_plan.id, dimension="stores", value=2, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=low_plan.id, dimension="users", value=5, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=low_plan.id, dimension="products", value=50, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=high_plan.id, dimension="stores", value=10, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=high_plan.id, dimension="users", value=25, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=high_plan.id, dimension="products", value=500, is_unlimited=False),
    ])
    db.commit()

    # Point tenant to starter plan
    sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t_data["tenant_id"]).first()
    sub.plan_id = low_plan.id
    sub.unit_price = low_plan.price
    sub.status = "active"
    db.commit()

    # 1. Request Upgrade to Growth Tier
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": high_plan.id},
        headers=headers,
    )
    assert r.status_code == 200
    resp_data = r.json()
    assert resp_data["change_type"] == "upgrade"
    assert resp_data["status"] == "pending_payment"
    assert resp_data["effective_timing"] == "after_payment_verification"
    assert resp_data["target_plan_id"] == high_plan.id
    assert resp_data["invoice_id"] is not None
    invoice_id = resp_data["invoice_id"]

    # Verify active plan is UNCHANGED (U1=B)
    db.refresh(sub)
    assert sub.plan_id == low_plan.id
    assert sub.pending_plan_id == high_plan.id
    assert sub.unit_price == low_plan.price

    # 2. Idempotency: Repeating request returns exact same unpaid invoice without duplicates
    r2 = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": high_plan.id},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["invoice_id"] == invoice_id

    # 3. Pay via UPI and verify payment
    # Initiate checkout
    init_r = client.post(
        f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice_id}",
        headers=headers,
    )
    assert init_r.status_code == 201
    ref = init_r.json()["reference"]

    # Submit UTR
    utr_val = f"UTR{uuid.uuid4().hex[:10].upper()}"
    submit_r = client.post(
        "/api/v1/saas-billing/upi/submit",
        json={
            "reference": ref,
            "utr": utr_val,
            "payer_vpa": "customer@upi",
        },
        headers=headers,
    )
    assert submit_r.status_code == 200

    # Super Admin verifies transaction
    verify_r = client.post(
        f"/api/v1/super-admins/upi-transactions/{ref}/verify",
        headers=active_super_admin["headers"],
    )
    assert verify_r.status_code == 200

    # 4. Assert subscription is now on Growth Tier and pending_plan_id is cleared
    db.refresh(sub)
    assert sub.plan_id == high_plan.id
    assert sub.pending_plan_id is None
    assert sub.unit_price == high_plan.price
    assert sub.status == "active"

    # Verify invoice is paid
    inv = db.query(SaaSInvoice).filter(SaaSInvoice.id == invoice_id).first()
    assert inv.status == "paid"

    # Verify entitlements expanded to 10 stores
    ent_svc = SaaSEntitlementService(db)
    limit, is_unlim = ent_svc.get_limit(t_data["tenant_id"], "stores")
    assert limit == 10


def test_downgrade_flow_and_period_end_lifecycle(db: Session):
    t_data = create_test_tenant("dwgflow")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    # Create high and low plans
    high_plan = SaaSPlan(
        name="Enterprise Tier",
        code=f"ent_{uuid.uuid4().hex[:6]}",
        price=Decimal("4000.00"),
        currency="INR",
        is_active=True,
    )
    low_plan = SaaSPlan(
        name="Basic Tier",
        code=f"bas_{uuid.uuid4().hex[:6]}",
        price=Decimal("1000.00"),
        currency="INR",
        is_active=True,
    )
    db.add_all([high_plan, low_plan])
    db.commit()

    db.add_all([
        SaaSPlanEntitlement(plan_id=high_plan.id, dimension="stores", value=15, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=high_plan.id, dimension="users", value=30, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=high_plan.id, dimension="products", value=1000, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=low_plan.id, dimension="stores", value=3, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=low_plan.id, dimension="users", value=5, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=low_plan.id, dimension="products", value=100, is_unlimited=False),
    ])
    db.commit()

    # Point tenant to Enterprise Tier
    sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t_data["tenant_id"]).first()
    sub.plan_id = high_plan.id
    sub.unit_price = high_plan.price
    sub.status = "active"
    db.commit()

    # Create 5 stores under tenant (usage = 5, target plan limit = 3) -> D2=B over-quota test!
    for i in range(5):
        s = Store(
            tenant_id=t_data["tenant_id"],
            name=f"Store {i+1}",
            code=f"ST-{uuid.uuid4().hex[:6].upper()}",
            is_active=True,
        )
        db.add(s)
    db.commit()

    # 1. Request Downgrade to Basic Tier
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": low_plan.id},
        headers=headers,
    )
    assert r.status_code == 200
    resp_data = r.json()
    assert resp_data["change_type"] == "downgrade"
    assert resp_data["status"] == "scheduled"
    assert resp_data["effective_timing"] == "period_end"
    assert resp_data["target_plan_id"] == low_plan.id
    assert resp_data["invoice_id"] is None

    # Current plan and stores remain untouched
    db.refresh(sub)
    assert sub.plan_id == high_plan.id
    assert sub.scheduled_plan_id == low_plan.id

    stores_count = db.query(Store).filter(Store.tenant_id == t_data["tenant_id"]).count()
    assert stores_count == 5

    # 2. Advance time past current_period_end to simulate period arrival
    sub.current_period_end = datetime.utcnow() - timedelta(days=1)
    db.commit()

    # 3. Run lifecycle processor
    lifecycle_svc = SaaSSubscriptionLifecycleService(db)
    summary = lifecycle_svc.run_all(tenant_id=t_data["tenant_id"])
    assert summary["scheduled_plan_changes_applied"] == 1

    # 4. Verify subscription has downgraded to Basic Tier and scheduled_plan_id is cleared
    db.refresh(sub)
    assert sub.plan_id == low_plan.id
    assert sub.scheduled_plan_id is None
    assert sub.unit_price == low_plan.price

    # Verify stores are STILL intact (zero deletion / zero deactivation)
    stores_count = db.query(Store).filter(Store.tenant_id == t_data["tenant_id"]).count()
    assert stores_count == 5

    # 5. Future creation fails closed via require_limit()
    ent_svc = SaaSEntitlementService(db)
    with pytest.raises(Exception) as excinfo:
        ent_svc.require_limit(t_data["tenant_id"], "stores")
    assert "quota exceeded" in str(excinfo.value).lower()

    # 6. Idempotency: running lifecycle again applies 0 transitions
    summary2 = lifecycle_svc.run_all(tenant_id=t_data["tenant_id"])
    assert summary2["scheduled_plan_changes_applied"] == 0


def test_cancel_pending_upgrade_and_scheduled_downgrade(db: Session):
    t_data = create_test_tenant("cancelchg")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    plan_a = SaaSPlan(name="Plan A", code=f"pa_{uuid.uuid4().hex[:6]}", price=Decimal("100.00"), is_active=True)
    plan_b = SaaSPlan(name="Plan B", code=f"pb_{uuid.uuid4().hex[:6]}", price=Decimal("300.00"), is_active=True)
    plan_c = SaaSPlan(name="Plan C", code=f"pc_{uuid.uuid4().hex[:6]}", price=Decimal("50.00"), is_active=True)
    db.add_all([plan_a, plan_b, plan_c])
    db.commit()

    sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t_data["tenant_id"]).first()
    sub.plan_id = plan_a.id
    sub.unit_price = plan_a.price
    sub.status = "active"
    db.commit()

    # Test 1: Upgrade to Plan B, then cancel
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": plan_b.id},
        headers=headers,
    )
    assert r.status_code == 200
    inv_id = r.json()["invoice_id"]

    db.refresh(sub)
    assert sub.pending_plan_id == plan_b.id

    cancel_r = client.post(
        "/api/v1/saas-billing/subscription/cancel-change",
        headers=headers,
    )
    assert cancel_r.status_code == 200
    assert cancel_r.json()["cancelled_change_type"] == "upgrade"

    db.refresh(sub)
    assert sub.pending_plan_id is None
    # Verify invoice was cancelled
    inv = db.query(SaaSInvoice).filter(SaaSInvoice.id == inv_id).first()
    assert inv.status == "cancelled"

    # Test 2: Downgrade to Plan C, then cancel
    r_down = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": plan_c.id},
        headers=headers,
    )
    assert r_down.status_code == 200
    db.refresh(sub)
    assert sub.scheduled_plan_id == plan_c.id

    cancel_down = client.post(
        "/api/v1/saas-billing/subscription/cancel-change",
        headers=headers,
    )
    assert cancel_down.status_code == 200
    assert cancel_down.json()["cancelled_change_type"] == "downgrade"

    db.refresh(sub)
    assert sub.scheduled_plan_id is None

    # Test 3: Calling cancel when nothing is pending returns 400
    r_empty = client.post(
        "/api/v1/saas-billing/subscription/cancel-change",
        headers=headers,
    )
    assert r_empty.status_code == 400


def test_terminal_subscription_cannot_change_plan(db: Session):
    t_data = create_test_tenant("termsafe")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t_data["tenant_id"]).first()
    sub.status = "cancelled"
    db.commit()

    # Try change plan
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": 2},
        headers=headers,
    )
    assert r.status_code == 400
    assert "cannot change plan" in r.json()["detail"]["message"].lower()

    sub.status = "expired"
    db.commit()

    r2 = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": 2},
        headers=headers,
    )
    assert r2.status_code == 400
    assert "cannot change plan" in r2.json()["detail"]["message"].lower()


def test_rejected_payment_does_not_activate_plan(db: Session, active_super_admin):
    t_data = create_test_tenant("rejups")
    headers = {"Authorization": f"Bearer {t_data['token']}"}

    plan_orig = SaaSPlan(name="Orig Plan", code=f"orig_{uuid.uuid4().hex[:6]}", price=Decimal("100.00"), is_active=True)
    plan_upg = SaaSPlan(name="Upg Plan", code=f"upg_{uuid.uuid4().hex[:6]}", price=Decimal("500.00"), is_active=True)
    db.add_all([plan_orig, plan_upg])
    db.commit()

    sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t_data["tenant_id"]).first()
    sub.plan_id = plan_orig.id
    sub.unit_price = plan_orig.price
    sub.status = "active"
    db.commit()

    # 1. Request upgrade
    r = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": plan_upg.id},
        headers=headers,
    )
    assert r.status_code == 200
    inv_id = r.json()["invoice_id"]

    # 2. Initiate checkout & submit UTR
    init_r = client.post(
        f"/api/v1/saas-billing/upi/initiate?invoice_id={inv_id}",
        headers=headers,
    )
    assert init_r.status_code == 201
    ref = init_r.json()["reference"]

    client.post(
        "/api/v1/saas-billing/upi/submit",
        json={"reference": ref, "utr": "INVALID123", "payer_vpa": "fake@upi"},
        headers=headers,
    )

    # 3. Super admin REJECTS payment
    rej_r = client.post(
        f"/api/v1/super-admins/upi-transactions/{ref}/reject",
        json={"rejection_reason": "Invalid payment proof"},
        headers=active_super_admin["headers"],
    )
    assert rej_r.status_code == 200

    # 4. Assert subscription is STILL on original plan!
    db.refresh(sub)
    assert sub.plan_id == plan_orig.id
    assert sub.pending_plan_id == plan_upg.id  # Still pending, not activated
    assert sub.unit_price == plan_orig.price


def test_cross_tenant_isolation_on_plan_change(db: Session):
    t_a = create_test_tenant("tisoa")
    t_b = create_test_tenant("tisob")

    headers_a = {"Authorization": f"Bearer {t_a['token']}"}
    headers_b = {"Authorization": f"Bearer {t_b['token']}"}

    # Tenant B requests upgrade
    r_b = client.post(
        "/api/v1/saas-billing/subscription/change",
        json={"target_plan_id": 2},
        headers=headers_b,
    )
    if r_b.status_code == 200:
        inv_id_b = r_b.json().get("invoice_id")
        if inv_id_b:
            # Tenant A attempts to view Tenant B's invoice -> must return 404
            r_cross_inv = client.get(
                f"/api/v1/saas-billing/invoices/{inv_id_b}",
                headers=headers_a,
            )
            assert r_cross_inv.status_code == 404

    # Tenant A views own subscription
    r_sub_a = client.get("/api/v1/saas-billing/subscription", headers=headers_a)
    assert r_sub_a.status_code == 200
    assert r_sub_a.json()["tenant_id"] == t_a["tenant_id"]

