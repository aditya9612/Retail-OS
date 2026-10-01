from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
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
def super_admin_auth():
    uid = uuid.uuid4().hex[:6]
    name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
    email = f"sa_plan_{uid}@example.com"
    password = "SuperPassword@123!"
    session = SessionLocal()
    try:
        sa_data = SuperAdminCreate(
            email=email,
            full_name=f"Super Admin {name_suffix}",
            password=password,
            phone="9876543210",
        )
        SuperAdminService(session).create_super_admin(sa_data)
    finally:
        session.close()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={"email": email, "password": password},
    )
    assert login_r.status_code == 200, f"Super Admin login failed: {login_r.text}"
    token = login_r.json()["access_token"]
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def tenant_auth():
    uid = uuid.uuid4().hex[:6]
    email = f"tenant_plan_{uid}@example.com"
    password = "TenantPassword@123!"
    reg_payload = {
        "tenant_name": f"Tenant {uid}",
        "domain": f"tp-{uid}",
        "email": email,
        "admin_name": f"Admin {uid}",
        "password": password,
        "phone": f"91{uuid.uuid4().int % 100000000:08d}",
    }
    r = client.post("/api/v1/auth/register", json=reg_payload)
    assert r.status_code == 200, f"Tenant registration failed: {r.text}"
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


# ==============================================================================
# 1. AUTHORIZATION TESTS
# ==============================================================================


def test_auth_anonymous_requests_rejected():
    """Verify anonymous access is rejected with 401 across all 6 endpoints."""
    endpoints = [
        ("POST", "/api/v1/super-admins/saas-plans", {"name": "Test", "code": "test"}),
        ("GET", "/api/v1/super-admins/saas-plans", None),
        ("GET", "/api/v1/super-admins/saas-plans/1", None),
        ("PATCH", "/api/v1/super-admins/saas-plans/1", {"name": "Test"}),
        ("PATCH", "/api/v1/super-admins/saas-plans/1/activate", None),
        ("PATCH", "/api/v1/super-admins/saas-plans/1/deactivate", None),
    ]

    for method, path, json_data in endpoints:
        if method == "POST":
            r = client.post(path, json=json_data)
        elif method == "GET":
            r = client.get(path)
        elif method == "PATCH":
            r = client.patch(path, json=json_data)
        assert r.status_code == 401, f"Expected 401 for anonymous {method} {path}, got {r.status_code}"


def test_auth_tenant_users_rejected(tenant_auth):
    """Verify tenant tokens cannot access platform-level SaaS plan endpoints."""
    headers = tenant_auth["headers"]
    endpoints = [
        ("POST", "/api/v1/super-admins/saas-plans", {"name": "Test", "code": "test"}),
        ("GET", "/api/v1/super-admins/saas-plans", None),
        ("GET", "/api/v1/super-admins/saas-plans/1", None),
        ("PATCH", "/api/v1/super-admins/saas-plans/1", {"name": "Test"}),
        ("PATCH", "/api/v1/super-admins/saas-plans/1/activate", None),
        ("PATCH", "/api/v1/super-admins/saas-plans/1/deactivate", None),
    ]

    for method, path, json_data in endpoints:
        if method == "POST":
            r = client.post(path, json=json_data, headers=headers)
        elif method == "GET":
            r = client.get(path, headers=headers)
        elif method == "PATCH":
            r = client.patch(path, json=json_data, headers=headers)
        assert r.status_code == 401, f"Expected 401 for tenant token on {method} {path}, got {r.status_code}"


# ==============================================================================
# 2. CREATE PLAN TESTS & VALIDATION
# ==============================================================================


def test_create_plan_valid(super_admin_auth):
    """Verify successful plan creation with custom metadata and defaults."""
    uid = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Growth Plan {uid}",
        "code": f"growth-{uid}",
        "description": "Designed for multi-outlet retail brands.",
        "price": 3499.00,
        "currency": "INR",
        "billing_interval": "monthly",
        "trial_days": 21,
        "is_active": True,
    }
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json=payload,
        headers=super_admin_auth["headers"],
    )
    assert r.status_code == 201, f"Expected 201 Created: {r.text}"
    data = r.json()
    assert data["name"] == payload["name"]
    assert data["code"] == payload["code"]
    assert data["description"] == payload["description"]
    assert float(data["price"]) == 3499.00
    assert data["currency"] == "INR"
    assert data["billing_interval"] == "monthly"
    assert data["trial_days"] == 21
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_plan_code_normalization(super_admin_auth):
    """Verify code is normalized to lowercase and stripped."""
    uid = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Normalized Plan {uid}",
        "code": f"  NORM-Plan_{uid}  ",
        "price": 1200.00,
    }
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json=payload,
        headers=super_admin_auth["headers"],
    )
    assert r.status_code == 201
    data = r.json()
    assert data["code"] == f"norm-plan_{uid}"


def test_create_plan_duplicate_code_conflict(super_admin_auth):
    """Verify creating a plan with an existing code returns HTTP 409 Conflict."""
    uid = uuid.uuid4().hex[:6]
    code = f"dupe-{uid}"
    payload1 = {
        "name": f"First Dupe {uid}",
        "code": code,
        "price": 999.00,
    }
    r1 = client.post(
        "/api/v1/super-admins/saas-plans",
        json=payload1,
        headers=super_admin_auth["headers"],
    )
    assert r1.status_code == 201

    payload2 = {
        "name": f"Second Dupe {uid}",
        "code": code.upper(),  # case-insensitive check
        "price": 1499.00,
    }
    r2 = client.post(
        "/api/v1/super-admins/saas-plans",
        json=payload2,
        headers=super_admin_auth["headers"],
    )
    assert r2.status_code == 409, f"Expected 409 Conflict, got {r2.status_code}: {r2.text}"


def test_create_plan_validation_errors(super_admin_auth):
    """Verify input validation rejects invalid price, interval, trial days, name, code."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]

    # Negative price
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": "P", "code": f"p-{uid}", "price": -10.00},
        headers=headers,
    )
    assert r.status_code == 422

    # Negative trial days
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": "P", "code": f"p-{uid}", "price": 100.00, "trial_days": -1},
        headers=headers,
    )
    assert r.status_code == 422

    # Invalid billing interval
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": "P", "code": f"p-{uid}", "price": 100.00, "billing_interval": "quarterly"},
        headers=headers,
    )
    assert r.status_code == 422

    # Empty name
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": "   ", "code": f"p-{uid}", "price": 100.00},
        headers=headers,
    )
    assert r.status_code == 422

    # Empty code
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": "Valid Name", "code": "   ", "price": 100.00},
        headers=headers,
    )
    assert r.status_code == 422

    # Invalid code characters
    r = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": "Valid Name", "code": "code with spaces!", "price": 100.00},
        headers=headers,
    )
    assert r.status_code == 422


# ==============================================================================
# 3. LIST & SEARCH & FILTER TESTS
# ==============================================================================


def test_list_plans_pagination_and_deterministic_order(super_admin_auth):
    """Verify list returns paginated structure with total, pages, and descending order."""
    r = client.get(
        "/api/v1/super-admins/saas-plans?page=1&page_size=2",
        headers=super_admin_auth["headers"],
    )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "page" in data
    assert "page_size" in data
    assert "total" in data
    assert "total_pages" in data
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2
    assert data["total"] >= 3  # at least baseline plans exist

    # Verify deterministic ordering: created_at desc, id desc
    if len(data["items"]) >= 2:
        assert data["items"][0]["id"] > data["items"][1]["id"] or data["items"][0]["created_at"] >= data["items"][1]["created_at"]


def test_list_plans_search_by_name_and_code(super_admin_auth):
    """Verify case-insensitive search by plan name and code."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]
    client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"Searchable Alpha {uid}", "code": f"alpha-{uid}", "price": 1500.00},
        headers=headers,
    )

    # Search by name substring
    r_name = client.get(
        f"/api/v1/super-admins/saas-plans?search=Searchable",
        headers=headers,
    )
    assert r_name.status_code == 200
    names = [p["name"] for p in r_name.json()["items"]]
    assert any(f"Searchable Alpha {uid}" in n for n in names)

    # Search by code
    r_code = client.get(
        f"/api/v1/super-admins/saas-plans?search=alpha-{uid}",
        headers=headers,
    )
    assert r_code.status_code == 200
    codes = [p["code"] for p in r_code.json()["items"]]
    assert f"alpha-{uid}" in codes


def test_list_plans_active_filter(super_admin_auth):
    """Verify filtering by is_active=true and is_active=false."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]
    # Create an inactive plan
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"Inactive Plan {uid}", "code": f"inact-{uid}", "price": 500.00, "is_active": False},
        headers=headers,
    )
    assert r_create.status_code == 201

    # Filter active only
    r_active = client.get("/api/v1/super-admins/saas-plans?is_active=true", headers=headers)
    assert r_active.status_code == 200
    for plan in r_active.json()["items"]:
        assert plan["is_active"] is True

    # Filter inactive only
    r_inactive = client.get("/api/v1/super-admins/saas-plans?is_active=false", headers=headers)
    assert r_inactive.status_code == 200
    for plan in r_inactive.json()["items"]:
        assert plan["is_active"] is False
    inactive_codes = [p["code"] for p in r_inactive.json()["items"]]
    assert f"inact-{uid}" in inactive_codes


# ==============================================================================
# 4. DETAIL TESTS
# ==============================================================================


def test_get_plan_detail_success_and_not_found(super_admin_auth):
    """Verify detail retrieves all safe fields, and 404 for non-existent id."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"Detail Plan {uid}", "code": f"det-{uid}", "price": 750.00},
        headers=headers,
    )
    assert r_create.status_code == 201
    plan_id = r_create.json()["id"]

    r_detail = client.get(f"/api/v1/super-admins/saas-plans/{plan_id}", headers=headers)
    assert r_detail.status_code == 200
    detail = r_detail.json()
    assert detail["id"] == plan_id
    assert detail["code"] == f"det-{uid}"
    assert float(detail["price"]) == 750.00

    # Non-existent
    r_404 = client.get("/api/v1/super-admins/saas-plans/999999", headers=headers)
    assert r_404.status_code == 404


# ==============================================================================
# 5. UPDATE TESTS & PATCH SEMANTICS
# ==============================================================================


def test_update_plan_partial_and_description_clearing(super_admin_auth):
    """Verify PATCH partial update semantics, including description clearing vs preservation."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={
            "name": f"Orig Name {uid}",
            "code": f"orig-{uid}",
            "description": "Original description text",
            "price": 1000.00,
            "trial_days": 14,
        },
        headers=headers,
    )
    assert r_create.status_code == 201
    plan_id = r_create.json()["id"]

    # 1. Partial update only price -> description MUST remain intact
    r_up1 = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"price": 1250.00},
        headers=headers,
    )
    assert r_up1.status_code == 200
    data1 = r_up1.json()
    assert float(data1["price"]) == 1250.00
    assert data1["description"] == "Original description text"
    assert data1["name"] == f"Orig Name {uid}"

    # 2. Explicitly clear description -> {"description": null}
    r_up2 = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"description": None},
        headers=headers,
    )
    assert r_up2.status_code == 200
    data2 = r_up2.json()
    assert data2["description"] is None
    assert float(data2["price"]) == 1250.00

    # 3. Code must be immutable (cannot change code even if provided)
    r_up3 = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"code": "hacked-code", "name": f"New Name {uid}"},
        headers=headers,
    )
    assert r_up3.status_code == 200
    data3 = r_up3.json()
    assert data3["name"] == f"New Name {uid}"
    assert data3["code"] == f"orig-{uid}"  # code remained unchanged!


def test_update_plan_validation_and_not_found(super_admin_auth):
    """Verify invalid values in PATCH are rejected with 422, and non-existent id returns 404."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"Val Plan {uid}", "code": f"val-{uid}", "price": 1000.00},
        headers=headers,
    )
    assert r_create.status_code == 201
    plan_id = r_create.json()["id"]

    # Negative price rejected
    r = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"price": -50.00},
        headers=headers,
    )
    assert r.status_code == 422

    # Null price rejected
    r = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"price": None},
        headers=headers,
    )
    assert r.status_code == 422

    # Negative trial days rejected
    r = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"trial_days": -5},
        headers=headers,
    )
    assert r.status_code == 422

    # Non-existent plan 404
    r = client.patch(
        "/api/v1/super-admins/saas-plans/999999",
        json={"name": "Ghost"},
        headers=headers,
    )
    assert r.status_code == 404


# ==============================================================================
# 6. CRITICAL PRICE SNAPSHOT RULE VERIFICATION
# ==============================================================================


def test_price_snapshot_rule_preserved_on_plan_update(super_admin_auth, db_session):
    """
    CRITICAL: Updating a plan's price in saas_plans must NOT alter existing subscriptions' unit_price.
    Existing subscriptions retain their historical price snapshot.
    """
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]

    # 1. Create a custom plan at 2499.00
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"Snapshot Plan {uid}", "code": f"snap-{uid}", "price": 2499.00},
        headers=headers,
    )
    assert r_create.status_code == 201
    plan_id = r_create.json()["id"]

    # 2. Create a test tenant and subscription referencing this plan at unit_price = 2499.00
    tenant = Tenant(
        name=f"Snapshot Tenant {uid}",
        domain=f"snap-{uid}",
        is_active=True,
        plan=f"snap-{uid}",
        subscription_status="active",
    )
    db_session.add(tenant)
    db_session.flush()

    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=plan_id,
        status="active",
        billing_interval="monthly",
        unit_price=Decimal("2499.00"),
        currency="INR",
        start_date=datetime.now(timezone.utc),
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc),
        trial_end_date=None,
        cancel_at_period_end=False,
    )
    db_session.add(sub)
    db_session.commit()
    sub_id = sub.id

    # 3. Super Admin updates plan price: 2499.00 -> 2999.00
    r_update = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        json={"price": 2999.00},
        headers=headers,
    )
    assert r_update.status_code == 200
    assert float(r_update.json()["price"]) == 2999.00

    # 4. Assert plan price in DB is 2999.00
    db_session.expire_all()
    plan_db = db_session.query(SaaSPlan).filter(SaaSPlan.id == plan_id).one()
    assert plan_db.price == Decimal("2999.00")

    # 5. Assert EXISTING subscription's unit_price remains 2499.00!
    sub_db = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).one()
    assert sub_db.unit_price == Decimal("2499.00"), f"Expected 2499.00, got {sub_db.unit_price}"


# ==============================================================================
# 7. ACTIVATE & DEACTIVATE TESTS
# ==============================================================================


def test_activate_and_deactivate_plan_lifecycle(super_admin_auth, db_session):
    """Verify activate and deactivate endpoints update is_active without modifying subscriptions."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]

    # Create active plan
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"Lifecycle Plan {uid}", "code": f"life-{uid}", "price": 1999.00, "is_active": True},
        headers=headers,
    )
    assert r_create.status_code == 201
    plan_id = r_create.json()["id"]

    # Attach a subscription to verify it remains intact
    tenant = Tenant(
        name=f"Life Tenant {uid}",
        domain=f"life-{uid}",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()

    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=plan_id,
        status="active",
        billing_interval="monthly",
        unit_price=Decimal("1999.00"),
        currency="INR",
        start_date=datetime.now(timezone.utc),
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc),
        cancel_at_period_end=False,
    )
    db_session.add(sub)
    db_session.commit()
    sub_id = sub.id

    # 1. Deactivate plan
    r_deact = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}/deactivate",
        headers=headers,
    )
    assert r_deact.status_code == 200
    assert r_deact.json()["is_active"] is False

    # Check DB plan is inactive
    db_session.expire_all()
    plan_db = db_session.query(SaaSPlan).filter(SaaSPlan.id == plan_id).one()
    assert plan_db.is_active is False

    # Check subscription is untouched and remains active
    sub_db = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).one()
    assert sub_db.status == "active"
    assert sub_db.plan_id == plan_id

    # 2. Reactivate plan
    r_act = client.patch(
        f"/api/v1/super-admins/saas-plans/{plan_id}/activate",
        headers=headers,
    )
    assert r_act.status_code == 200
    assert r_act.json()["is_active"] is True

    db_session.expire_all()
    plan_db2 = db_session.query(SaaSPlan).filter(SaaSPlan.id == plan_id).one()
    assert plan_db2.is_active is True

    # 3. Deactivate / activate non-existent plan returns 404
    r_404_1 = client.patch("/api/v1/super-admins/saas-plans/999999/deactivate", headers=headers)
    assert r_404_1.status_code == 404
    r_404_2 = client.patch("/api/v1/super-admins/saas-plans/999999/activate", headers=headers)
    assert r_404_2.status_code == 404


# ==============================================================================
# 8. NO PHYSICAL DELETE TEST
# ==============================================================================


def test_no_physical_delete_allowed(super_admin_auth):
    """Verify DELETE /saas-plans/{plan_id} is NOT implemented and returns 405 Method Not Allowed."""
    headers = super_admin_auth["headers"]
    uid = uuid.uuid4().hex[:6]
    r_create = client.post(
        "/api/v1/super-admins/saas-plans",
        json={"name": f"No Delete {uid}", "code": f"nodelete-{uid}", "price": 800.00},
        headers=headers,
    )
    assert r_create.status_code == 201
    plan_id = r_create.json()["id"]

    # Attempt physical deletion
    r_del = client.delete(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        headers=headers,
    )
    assert r_del.status_code == 405, f"Expected 405 Method Not Allowed, got {r_del.status_code}"

    # Plan still exists in DB
    r_get = client.get(
        f"/api/v1/super-admins/saas-plans/{plan_id}",
        headers=headers,
    )
    assert r_get.status_code == 200
