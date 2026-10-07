import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSPlan,
    SaaSSubscription,
    SaaSUPITransaction,
)
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.store import Store
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.super_admin import SuperAdminCreate
from app.services.super_admin_service import SuperAdminService

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def super_admin_auth(db_session):
    uid = uuid.uuid4().hex[:6]
    name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
    email = f"sa_mgmt_{uid}@example.com"
    password = "SuperPassword@123!"
    db_session.query(SuperAdmin).delete()
    db_session.commit()
    data = SuperAdminCreate(
        email=email,
        full_name=f"Super Admin {name_suffix}",
        password=password,
        phone="9876543210",
    )
    SuperAdminService(db_session).create_super_admin(data)
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={"email": email, "password": password},
    )
    assert login_r.status_code == 200, f"Super admin login failed: {login_r.text}"
    token = login_r.json()["access_token"]
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def tenant_auth(db_session):
    uid = uuid.uuid4().hex[:6]
    email = f"tenant_{uid}@example.com"
    password = "TenantPassword@123!"
    reg_payload = {
        "tenant_name": f"Tenant {uid}",
        "domain": f"t-{uid}",
        "email": email,
        "admin_name": f"Admin {uid}",
        "password": password,
        "phone": f"91{uuid.uuid4().int % 100000000:08d}",
    }
    r = client.post("/api/v1/auth/register", json=reg_payload)
    assert r.status_code == 200, f"Registration failed: {r.text}"
    tenant_id = r.json()["tenant_id"]

    login_r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]

    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def saas_setup(db_session):
    uid = uuid.uuid4().hex[:6]

    # Create plans
    plan_basic = SaaSPlan(
        code=f"basic_{uid}",
        name=f"Basic Plan {uid}",
        description="Basic Tier",
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    plan_pro = SaaSPlan(
        code=f"pro_{uid}",
        name=f"Pro Plan {uid}",
        description="Pro Tier",
        price=Decimal("2999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    plan_enterprise = SaaSPlan(
        code=f"ent_{uid}",
        name=f"Enterprise Plan {uid}",
        description="Enterprise Tier",
        price=Decimal("9999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    db_session.add_all([plan_basic, plan_pro, plan_enterprise])
    db_session.flush()

    # Plan entitlements for basic
    db_session.add_all([
        SaaSPlanEntitlement(plan_id=plan_basic.id, dimension="stores", value=2, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=plan_basic.id, dimension="users", value=5, is_unlimited=False),
        SaaSPlanEntitlement(plan_id=plan_basic.id, dimension="products", value=100, is_unlimited=False),
    ])

    # Create 2 tenants
    tenant_a = Tenant(
        name=f"Tenant A {uid}",
        domain=f"domain-a-{uid}",
        is_active=True,
        plan=plan_basic.code,
        subscription_status="active",
    )
    tenant_b = Tenant(
        name=f"Tenant B {uid}",
        domain=f"domain-b-{uid}",
        is_active=True,
        plan=plan_pro.code,
        subscription_status="expired",
    )
    tenant_c = Tenant(
        name=f"Tenant C No Sub {uid}",
        domain=f"domain-c-{uid}",
        is_active=True,
    )
    db_session.add_all([tenant_a, tenant_b, tenant_c])
    db_session.flush()

    now = datetime.now(timezone.utc)

    # Sub A for Tenant A (active, with pending upgrade to Pro)
    sub_a = SaaSSubscription(
        tenant_id=tenant_a.id,
        plan_id=plan_basic.id,
        status="active",
        billing_interval="monthly",
        unit_price=Decimal("999.00"),
        currency="INR",
        start_date=now - timedelta(days=30),
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        trial_end_date=None,
        cancel_at_period_end=False,
        pending_plan_id=plan_pro.id,
        scheduled_plan_id=None,
    )
    # Sub B for Tenant B (expired, with scheduled downgrade to Basic)
    sub_b = SaaSSubscription(
        tenant_id=tenant_b.id,
        plan_id=plan_pro.id,
        status="expired",
        billing_interval="monthly",
        unit_price=Decimal("2999.00"),
        currency="INR",
        start_date=now - timedelta(days=60),
        current_period_start=now - timedelta(days=30),
        current_period_end=now - timedelta(days=1),
        trial_end_date=None,
        cancel_at_period_end=False,
        pending_plan_id=None,
        scheduled_plan_id=plan_basic.id,
    )
    db_session.add_all([sub_a, sub_b])
    db_session.flush()

    tenant_a.current_subscription_id = sub_a.id
    tenant_b.current_subscription_id = sub_b.id

    # Add a store to Tenant A to verify usage
    store_a = Store(
        tenant_id=tenant_a.id,
        name=f"Store A1 {uid}",
        code=f"STA1_{uid}",
        is_active=True,
    )
    db_session.add(store_a)

    # Invoices for Tenant A
    inv_paid = SaaSInvoice(
        tenant_id=tenant_a.id,
        subscription_id=sub_a.id,
        invoice_number=f"INV-PAID-{uid}",
        billing_reason="subscription_cycle",
        subtotal=Decimal("999.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("999.00"),
        currency="INR",
        status="paid",
        due_date=now - timedelta(days=5),
        paid_at=now - timedelta(days=4),
    )
    inv_unpaid = SaaSInvoice(
        tenant_id=tenant_a.id,
        subscription_id=sub_a.id,
        invoice_number=f"INV-UPG-{uid}",
        billing_reason="plan_upgrade",
        subtotal=Decimal("2000.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("2000.00"),
        currency="INR",
        status="unpaid",
        due_date=now + timedelta(days=2),
    )
    inv_cancelled = SaaSInvoice(
        tenant_id=tenant_b.id,
        subscription_id=sub_b.id,
        invoice_number=f"INV-CANC-{uid}",
        billing_reason="manual_renewal",
        subtotal=Decimal("2999.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("2999.00"),
        currency="INR",
        status="cancelled",
        due_date=now - timedelta(days=10),
    )
    db_session.add_all([inv_paid, inv_unpaid, inv_cancelled])
    db_session.flush()

    # Add 2 UPI transactions for inv_unpaid (multiple payment attempts)
    upi_1 = SaaSUPITransaction(
        tenant_id=tenant_a.id,
        subscription_id=sub_a.id,
        invoice_id=inv_unpaid.id,
        reference=f"REF1_{uid}",
        upi_id="merchant@upi",
        amount=Decimal("2000.00"),
        currency="INR",
        status="rejected",
        rejection_reason="Incorrect UTR",
        created_at=now - timedelta(hours=2),
    )
    upi_2 = SaaSUPITransaction(
        tenant_id=tenant_a.id,
        subscription_id=sub_a.id,
        invoice_id=inv_unpaid.id,
        reference=f"REF2_{uid}",
        upi_id="merchant@upi",
        amount=Decimal("2000.00"),
        currency="INR",
        status="submitted",
        utr=f"UTR{uid}",
        created_at=now - timedelta(hours=1),
    )
    db_session.add_all([upi_1, upi_2])
    db_session.commit()

    return {
        "uid": uid,
        "plan_basic": plan_basic,
        "plan_pro": plan_pro,
        "plan_enterprise": plan_enterprise,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "tenant_c": tenant_c,
        "sub_a": sub_a,
        "sub_b": sub_b,
        "inv_paid": inv_paid,
        "inv_unpaid": inv_unpaid,
        "inv_cancelled": inv_cancelled,
        "upi_1": upi_1,
        "upi_2": upi_2,
    }


# ==========================================
# 1. AUTHORIZATION TESTS
# ==========================================

def test_auth_anonymous_rejected():
    """Anonymous requests must be rejected with 401."""
    assert client.get("/api/v1/super-admins/subscriptions").status_code == 401
    assert client.get("/api/v1/super-admins/tenants/1/subscription").status_code == 401
    assert client.get("/api/v1/super-admins/invoices").status_code == 401
    assert client.get("/api/v1/super-admins/invoices/1").status_code == 401


def test_auth_tenant_user_rejected(tenant_auth):
    """Tenant users must be rejected with 401/403."""
    headers = tenant_auth["headers"]
    assert client.get("/api/v1/super-admins/subscriptions", headers=headers).status_code in (401, 403)
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_auth['tenant_id']}/subscription", headers=headers).status_code in (401, 403)
    assert client.get("/api/v1/super-admins/invoices", headers=headers).status_code in (401, 403)
    assert client.get("/api/v1/super-admins/invoices/1", headers=headers).status_code in (401, 403)


def test_auth_super_admin_allowed(super_admin_auth):
    """Super Admin must be authorized (200)."""
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/subscriptions", headers=headers)
    assert r.status_code == 200
    r_inv = client.get("/api/v1/super-admins/invoices", headers=headers)
    assert r_inv.status_code == 200


# ==========================================
# 2. SUBSCRIPTION LISTING & FILTERS
# ==========================================

def test_subscription_list_pagination(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/subscriptions?page=1&page_size=1", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] >= 2
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert "subscription_id" in item
    assert "tenant_id" in item
    assert "tenant_name" in item
    assert "status" in item
    assert "current_plan" in item
    assert "unit_price" in item
    assert "currency" in item


def test_subscription_list_filter_status(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/subscriptions?status=active", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert all(item["status"] == "active" for item in data["items"])
    sub_ids = [item["subscription_id"] for item in data["items"]]
    assert saas_setup["sub_a"].id in sub_ids
    assert saas_setup["sub_b"].id not in sub_ids


def test_subscription_list_filter_invalid_status(super_admin_auth):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/subscriptions?status=invalid_status", headers=headers)
    assert r.status_code == 400


def test_subscription_list_filter_tenant_and_plan(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    tenant_a_id = saas_setup["tenant_a"].id
    plan_id = saas_setup["plan_basic"].id
    r = client.get(
        f"/api/v1/super-admins/subscriptions?tenant_id={tenant_a_id}&plan_id={plan_id}",
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["subscription_id"] == saas_setup["sub_a"].id


def test_subscription_list_filter_pending_and_scheduled(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    # Has pending plan
    r = client.get("/api/v1/super-admins/subscriptions?has_pending_plan=true", headers=headers)
    assert r.status_code == 200
    data = r.json()
    sub_ids = [item["subscription_id"] for item in data["items"]]
    assert saas_setup["sub_a"].id in sub_ids
    assert saas_setup["sub_b"].id not in sub_ids

    # Has scheduled plan
    r_sched = client.get("/api/v1/super-admins/subscriptions?has_scheduled_plan=true", headers=headers)
    assert r_sched.status_code == 200
    data_sched = r_sched.json()
    sched_sub_ids = [item["subscription_id"] for item in data_sched["items"]]
    assert saas_setup["sub_b"].id in sched_sub_ids
    assert saas_setup["sub_a"].id not in sched_sub_ids


# ==========================================
# 3. TENANT SUBSCRIPTION DETAIL
# ==========================================

def test_tenant_subscription_detail_valid(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    tenant_a_id = saas_setup["tenant_a"].id
    r = client.get(f"/api/v1/super-admins/tenants/{tenant_a_id}/subscription", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == tenant_a_id
    assert data["has_subscription"] is True
    assert data["subscription"]["id"] == saas_setup["sub_a"].id
    assert data["current_plan"]["code"] == saas_setup["plan_basic"].code
    assert data["pending_plan"]["code"] == saas_setup["plan_pro"].code
    assert data["scheduled_plan"] is None

    # Verify usage summary has stores, users, products
    dims = {u["dimension"]: u for u in data["usage_summary"]}
    assert "stores" in dims
    assert "users" in dims
    assert "products" in dims
    assert dims["stores"]["current_usage"] >= 1
    assert dims["stores"]["limit"] == 2
    assert dims["stores"]["is_unlimited"] is False

    # Verify recent invoices
    assert len(data["recent_invoices"]) >= 2
    inv_nums = [inv["invoice_number"] for inv in data["recent_invoices"]]
    assert saas_setup["inv_unpaid"].invoice_number in inv_nums

    # Verify latest unpaid invoice
    assert data["latest_unpaid_invoice"] is not None
    assert data["latest_unpaid_invoice"]["invoice_number"] == saas_setup["inv_unpaid"].invoice_number


def test_tenant_subscription_detail_no_subscription(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    tenant_c_id = saas_setup["tenant_c"].id
    r = client.get(f"/api/v1/super-admins/tenants/{tenant_c_id}/subscription", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == tenant_c_id
    assert data["has_subscription"] is False
    assert data["subscription"] is None
    assert data["current_plan"] is None
    assert data["latest_unpaid_invoice"] is None


def test_tenant_subscription_detail_not_found(super_admin_auth):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/tenants/999999/subscription", headers=headers)
    assert r.status_code == 404


def test_tenant_subscription_detail_mismatch_guard(super_admin_auth, saas_setup, db_session):
    headers = super_admin_auth["headers"]
    # Point Tenant C's current_subscription_id to Tenant A's subscription
    tenant_c = saas_setup["tenant_c"]
    tenant_c.current_subscription_id = saas_setup["sub_a"].id
    db_session.commit()

    r = client.get(f"/api/v1/super-admins/tenants/{tenant_c.id}/subscription", headers=headers)
    assert r.status_code == 409, f"Expected 409 conflict on tenant mismatch, got {r.status_code}: {r.text}"

    # Restore
    tenant_c.current_subscription_id = None
    db_session.commit()


# ==========================================
# 4. SAAS INVOICE LIST & FILTERS
# ==========================================

def test_invoice_list_pagination(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/invoices?page=1&page_size=2", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] >= 3
    assert len(data["items"]) == 2
    item = data["items"][0]
    assert "invoice_id" in item
    assert "invoice_number" in item
    assert "total_amount" in item
    assert "status" in item
    assert "tenant_name" in item


def test_invoice_list_filters(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]

    # Filter status: paid
    r_paid = client.get("/api/v1/super-admins/invoices?status=paid", headers=headers)
    assert r_paid.status_code == 200
    assert all(inv["status"] == "paid" for inv in r_paid.json()["items"])

    # Filter billing_reason: plan_upgrade
    r_upg = client.get("/api/v1/super-admins/invoices?billing_reason=plan_upgrade", headers=headers)
    assert r_upg.status_code == 200
    assert all(inv["billing_reason"] == "plan_upgrade" for inv in r_upg.json()["items"])

    # Filter tenant_id
    t_id = saas_setup["tenant_a"].id
    r_tenant = client.get(f"/api/v1/super-admins/invoices?tenant_id={t_id}", headers=headers)
    assert r_tenant.status_code == 200
    assert all(inv["tenant_id"] == t_id for inv in r_tenant.json()["items"])

    # Search invoice_number
    search_str = f"INV-UPG-{saas_setup['uid']}".lower()
    r_search = client.get(f"/api/v1/super-admins/invoices?search={search_str}", headers=headers)
    assert r_search.status_code == 200
    assert len(r_search.json()["items"]) == 1
    assert r_search.json()["items"][0]["invoice_number"] == saas_setup["inv_unpaid"].invoice_number


def test_invoice_list_invalid_status_and_reason(super_admin_auth):
    headers = super_admin_auth["headers"]
    # 'void' is NOT a valid status
    r_void = client.get("/api/v1/super-admins/invoices?status=void", headers=headers)
    assert r_void.status_code == 400

    # invalid billing reason
    r_bad_reason = client.get("/api/v1/super-admins/invoices?billing_reason=bad_reason", headers=headers)
    assert r_bad_reason.status_code == 400


# ==========================================
# 5. SAAS INVOICE DETAIL
# ==========================================

def test_invoice_detail_valid(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    inv_id = saas_setup["inv_unpaid"].id
    r = client.get(f"/api/v1/super-admins/invoices/{inv_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()

    # Invoice
    assert data["invoice"]["id"] == inv_id
    assert data["invoice"]["status"] == "unpaid"
    assert data["invoice"]["billing_reason"] == "plan_upgrade"

    # Tenant
    assert data["tenant"]["id"] == saas_setup["tenant_a"].id
    assert data["tenant"]["name"] == saas_setup["tenant_a"].name

    # Subscription & Plan
    assert data["subscription"]["id"] == saas_setup["sub_a"].id
    assert data["current_plan"]["code"] == saas_setup["plan_basic"].code

    # Multiple UPI payment attempts
    assert len(data["upi_transactions"]) == 2
    refs = [tx["reference"] for tx in data["upi_transactions"]]
    assert saas_setup["upi_1"].reference in refs
    assert saas_setup["upi_2"].reference in refs

    # Latest UPI transaction is the newest attempt (upi_2)
    assert data["latest_upi_transaction"] is not None
    assert data["latest_upi_transaction"]["reference"] == saas_setup["upi_2"].reference


def test_invoice_detail_not_found(super_admin_auth):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/invoices/999999", headers=headers)
    assert r.status_code == 404


# ==========================================
# 6. DASHBOARD METRICS
# ==========================================

def test_dashboard_extended_metrics(super_admin_auth, saas_setup):
    headers = super_admin_auth["headers"]
    r = client.get("/api/v1/super-admins/dashboard", headers=headers)
    assert r.status_code == 200
    data = r.json()

    # Preserved original fields
    assert "total_super_admins" in data
    assert "active_super_admins" in data
    assert "inactive_super_admins" in data
    assert "total_tenants" in data
    assert "active_tenants" in data
    assert "inactive_tenants" in data
    assert "total_users" in data

    # New Task 10 SaaS metrics
    assert "subscriptions_by_status" in data
    subs_map = data["subscriptions_by_status"]
    for status_key in ["trialing", "active", "past_due", "expired", "cancelled"]:
        assert status_key in subs_map
        assert isinstance(subs_map[status_key], int)

    assert data["expired_subscriptions_count"] >= 1
    assert data["pending_upgrades_count"] >= 1
    assert data["scheduled_downgrades_count"] >= 1

    # Cumulative paid SaaS invoice revenue
    assert "total_saas_revenue" in data
    rev = Decimal(str(data["total_saas_revenue"]))
    assert rev >= Decimal("999.00")
