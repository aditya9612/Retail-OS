from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.role import Role
from app.models.sale import Sale
from app.models.store import Store
from app.models.store_target import StoreTarget
from app.models.user import User
from app.schemas.store_target import (
    StoreTargetCreate,
    StoreTargetUpdate,
)

client = TestClient(app)


def create_tenant_client(prefix: str):
    """Helper to register and login a distinct tenant."""
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
        "slug": slug,
    }


@pytest.fixture
def tenant():
    return create_tenant_client("tgt-tenant")


@pytest.fixture
def other_tenant():
    return create_tenant_client("tgt-other")


@pytest.fixture
def stores(tenant):
    db = SessionLocal()
    try:
        s1 = Store(name="Main Store", code=f"M1-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=True)
        s2 = Store(name="Branch Store", code=f"B2-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=True)
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        return s1, s2
    finally:
        db.close()


# ==============================================================================
# 1. SCHEMA VALIDATION UNIT TESTS
# ==============================================================================

def test_schema_validations():
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # Valid schema passes
    valid = StoreTargetCreate(
        store_id=1,
        target_type="Sales Target",
        target_value=Decimal("50000.00"),
        period="monthly",
        start_date=now,
        end_date=later,
    )
    assert valid.target_type == "Sales Target"
    assert valid.period == "monthly"

    # Negative target_value
    with pytest.raises(Exception):
        StoreTargetCreate(
            store_id=1,
            target_type="Sales",
            target_value=Decimal("-100.00"),
            period="monthly",
            start_date=now,
            end_date=later,
        )

    # More than 2 decimal places
    with pytest.raises(Exception):
        StoreTargetCreate(
            store_id=1,
            target_type="Sales",
            target_value=Decimal("100.555"),
            period="monthly",
            start_date=now,
            end_date=later,
        )

    # End date <= start date
    with pytest.raises(Exception):
        StoreTargetCreate(
            store_id=1,
            target_type="Sales",
            target_value=Decimal("1000.00"),
            period="monthly",
            start_date=later,
            end_date=now,
        )

    # Invalid period
    with pytest.raises(Exception):
        StoreTargetCreate(
            store_id=1,
            target_type="Sales",
            target_value=Decimal("1000.00"),
            period="decade",
            start_date=now,
            end_date=later,
        )

    # Invalid target type (contains digits/symbols)
    with pytest.raises(Exception):
        StoreTargetCreate(
            store_id=1,
            target_type="Sales 123",
            target_value=Decimal("1000.00"),
            period="monthly",
            start_date=now,
            end_date=later,
        )

    # StoreTargetUpdate optional fields handle None
    upd = StoreTargetUpdate()
    assert upd.target_value is None
    assert upd.status is None

    # StoreTargetUpdate invalid status
    with pytest.raises(Exception):
        StoreTargetUpdate(status="random_status")


# ==============================================================================
# 2. CRUD API ENDPOINT TESTS
# ==============================================================================

def test_create_and_get_store_target(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    payload = {
        "store_id": s1.id,
        "target_type": "Monthly Revenue",
        "target_value": 75000.00,
        "period": "monthly",
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }

    # 1. Create target
    r = client.post("/api/v1/store-targets", json=payload, headers=tenant["headers"])
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"] is not None
    assert data["store_id"] == s1.id
    assert data["target_type"] == "Monthly Revenue"
    assert float(data["target_value"]) == 75000.00
    assert data["status"] == "active"
    target_id = data["id"]

    # 2. Get target by ID (Single target endpoint)
    r_get = client.get(f"/api/v1/store-targets/{target_id}", headers=tenant["headers"])
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["id"] == target_id

    # 3. List targets
    r_list = client.get(f"/api/v1/store-targets?store_id={s1.id}", headers=tenant["headers"])
    assert r_list.status_code == 200, r_list.text
    targets = r_list.json()
    assert any(t["id"] == target_id for t in targets)


def test_create_target_validation_errors(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # Nonexistent store ID
    payload_bad_store = {
        "store_id": 999999,
        "target_type": "Sales",
        "target_value": 5000.00,
        "period": "monthly",
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }
    r = client.post("/api/v1/store-targets", json=payload_bad_store, headers=tenant["headers"])
    assert r.status_code == 404, r.text
    assert "Store not found" in r.text

    # End date <= start date
    payload_bad_dates = {
        "store_id": s1.id,
        "target_type": "Sales",
        "target_value": 5000.00,
        "period": "monthly",
        "start_date": later.isoformat(),
        "end_date": now.isoformat(),
    }
    r = client.post("/api/v1/store-targets", json=payload_bad_dates, headers=tenant["headers"])
    assert r.status_code == 422, r.text


def test_create_target_overlap_conflict(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    payload = {
        "store_id": s1.id,
        "target_type": "Quarterly Sales",
        "target_value": 100000.00,
        "period": "quarterly",
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }

    # First target succeeds
    r1 = client.post("/api/v1/store-targets", json=payload, headers=tenant["headers"])
    assert r1.status_code == 201

    # Overlapping active target for same store and target_type fails with 409 Conflict
    r2 = client.post("/api/v1/store-targets", json=payload, headers=tenant["headers"])
    assert r2.status_code == 409, r2.text
    assert "already exists" in r2.text


def test_update_and_patch_store_target(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # Create target
    payload = {
        "store_id": s1.id,
        "target_type": "Update Test Target",
        "target_value": 20000.00,
        "period": "monthly",
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }
    r = client.post("/api/v1/store-targets", json=payload, headers=tenant["headers"])
    assert r.status_code == 201
    target_id = r.json()["id"]

    # PUT update value
    r_put = client.put(
        f"/api/v1/store-targets/{target_id}",
        json={"target_value": 25000.00},
        headers=tenant["headers"],
    )
    assert r_put.status_code == 200, r_put.text
    assert float(r_put.json()["target_value"]) == 25000.00

    # PATCH update status to completed
    r_patch = client.patch(
        f"/api/v1/store-targets/{target_id}",
        json={"status": "completed"},
        headers=tenant["headers"],
    )
    assert r_patch.status_code == 200, r_patch.text
    assert r_patch.json()["status"] == "completed"

    # Invalid status returns 422
    r_bad_status = client.patch(
        f"/api/v1/store-targets/{target_id}",
        json={"status": "unknown_status"},
        headers=tenant["headers"],
    )
    assert r_bad_status.status_code == 422


def test_delete_store_target(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    payload = {
        "store_id": s1.id,
        "target_type": "Delete Target",
        "target_value": 10000.00,
        "period": "monthly",
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }
    r = client.post("/api/v1/store-targets", json=payload, headers=tenant["headers"])
    assert r.status_code == 201
    target_id = r.json()["id"]

    # DELETE target
    r_del = client.delete(f"/api/v1/store-targets/{target_id}", headers=tenant["headers"])
    assert r_del.status_code == 204

    # Subsequent GET returns 404
    r_get = client.get(f"/api/v1/store-targets/{target_id}", headers=tenant["headers"])
    assert r_get.status_code == 404


def test_cross_tenant_isolation(tenant, other_tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # Tenant 1 creates a target
    r = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Secret Target",
            "target_value": 50000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert r.status_code == 201
    target_id = r.json()["id"]

    # Tenant 2 cannot GET target
    r2_get = client.get(f"/api/v1/store-targets/{target_id}", headers=other_tenant["headers"])
    assert r2_get.status_code == 404

    # Tenant 2 cannot UPDATE target
    r2_put = client.put(
        f"/api/v1/store-targets/{target_id}",
        json={"target_value": 1.00},
        headers=other_tenant["headers"],
    )
    assert r2_put.status_code == 404

    # Tenant 2 cannot DELETE target
    r2_del = client.delete(f"/api/v1/store-targets/{target_id}", headers=other_tenant["headers"])
    assert r2_del.status_code == 404


def test_store_scoped_user_restrictions(tenant, stores):
    s1, s2 = stores
    db = SessionLocal()
    try:
        # Create a manager role with stores:read and stores:write
        mgr_role = Role(
            tenant_id=tenant["tenant_id"],
            name=f"mgr-{uuid.uuid4().hex[:6]}",
            permissions=["stores:read", "stores:write"],
        )
        db.add(mgr_role)
        db.commit()
        db.refresh(mgr_role)

        # Create a user scoped strictly to s1
        user_email = f"manager-{uuid.uuid4().hex[:6]}@test.com"
        from app.core.security import get_password_hash
        mgr_user = User(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            role_id=mgr_role.id,
            email=user_email,
            full_name="Store One Manager",
            hashed_password=get_password_hash("Password123!"),
            is_active=True,
            is_deleted=False,
        )
        db.add(mgr_user)
        db.commit()
    finally:
        db.close()

    # Login as Store 1 Manager
    mgr_login = client.post("/api/v1/auth/login", json={"email": user_email, "password": "Password123!"})
    assert mgr_login.status_code == 200
    mgr_headers = {"Authorization": f"Bearer {mgr_login.json()['access_token']}"}

    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # Manager CAN create target for their assigned store s1
    r_ok = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Store One Target",
            "target_value": 30000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=mgr_headers,
    )
    assert r_ok.status_code == 201

    # Manager CANNOT create target for store s2 -> 403 Forbidden
    r_forbidden = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s2.id,
            "target_type": "Store Two Target",
            "target_value": 30000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=mgr_headers,
    )
    assert r_forbidden.status_code == 403, r_forbidden.text


def test_target_progress_tracking(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow() - timedelta(days=2)
    later = datetime.utcnow() + timedelta(days=28)

    # 1. Create a target of 1000.00
    r = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Progress Sales",
            "target_value": 1000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert r.status_code == 201
    target_id = r.json()["id"]

    # 2. Insert sales in that store within the target period
    db = SessionLocal()
    try:
        sale = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"SALE-{uuid.uuid4().hex[:8]}",
            subtotal=Decimal("400.00"),
            total_amount=Decimal("400.00"),
            payment_method="cash",
            payment_status="paid",
            created_at=datetime.utcnow(),
        )
        db.add(sale)
        db.commit()
    finally:
        db.close()

    # 3. Call progress endpoint
    r_prog = client.get(f"/api/v1/store-targets/{target_id}/progress", headers=tenant["headers"])
    assert r_prog.status_code == 200, r_prog.text
    p = r_prog.json()
    assert float(p["target_value"]) == 1000.00
    assert float(p["current_value"]) == 400.00
    assert float(p["achievement_percentage"]) == 40.0
    assert float(p["remaining_value"]) == 600.00
    assert p["is_achieved"] is False
    assert p["days_remaining"] >= 27


# ==============================================================================
# 3. COMPREHENSIVE PRODUCTION AUDIT EDGE-CASE TESTS
# ==============================================================================

def test_unauthorized_access_rejected():
    # Calling endpoints without auth header -> 401 Unauthorized
    assert client.get("/api/v1/store-targets").status_code == 401
    assert client.post("/api/v1/store-targets", json={}).status_code == 401
    assert client.get("/api/v1/store-targets/1").status_code == 401
    assert client.put("/api/v1/store-targets/1", json={}).status_code == 401
    assert client.patch("/api/v1/store-targets/1", json={}).status_code == 401
    assert client.delete("/api/v1/store-targets/1").status_code == 401
    assert client.get("/api/v1/store-targets/1/progress").status_code == 401

    # Invalid token -> 401 Unauthorized
    bad_headers = {"Authorization": "Bearer invalid_token_12345"}
    assert client.get("/api/v1/store-targets", headers=bad_headers).status_code == 401


def test_inactive_store_rejected(tenant):
    db = SessionLocal()
    try:
        inactive_store = Store(
            name="Closed Store",
            code=f"CLS-{uuid.uuid4().hex[:6]}",
            tenant_id=tenant["tenant_id"],
            is_active=False,
        )
        db.add(inactive_store)
        db.commit()
        db.refresh(inactive_store)
        in_id = inactive_store.id
    finally:
        db.close()

    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # Creating target for inactive store returns 404
    resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": in_id,
            "target_type": "Sales",
            "target_value": 5000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert resp.status_code == 404, resp.text
    assert "inactive" in resp.text.lower() or "not found" in resp.text.lower()


def test_date_validation_equal_and_reversed_dates(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()

    # Equal start and end date -> 422
    resp_equal = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Sales",
            "target_value": 5000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": now.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert resp_equal.status_code == 422, resp_equal.text

    # Reversed dates -> 422
    resp_reversed = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Sales",
            "target_value": 5000.00,
            "period": "monthly",
            "start_date": (now + timedelta(days=10)).isoformat(),
            "end_date": now.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert resp_reversed.status_code == 422, resp_reversed.text


def test_target_value_validation_zero_negative_and_excessive(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    base = {
        "store_id": s1.id,
        "target_type": "Sales",
        "period": "monthly",
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }

    # Zero target value -> 422
    r_zero = client.post("/api/v1/store-targets", json={**base, "target_value": 0.00}, headers=tenant["headers"])
    assert r_zero.status_code == 422, r_zero.text

    # Negative target value -> 422
    r_neg = client.post("/api/v1/store-targets", json={**base, "target_value": -100.00}, headers=tenant["headers"])
    assert r_neg.status_code == 422, r_neg.text

    # Excessive decimal places -> 422
    r_dec = client.post("/api/v1/store-targets", json={**base, "target_value": 100.555}, headers=tenant["headers"])
    assert r_dec.status_code == 422, r_dec.text

    # Exceeding column capacity (> 9,999,999,999.99) -> 422
    r_huge = client.post("/api/v1/store-targets", json={**base, "target_value": 10000000000.00}, headers=tenant["headers"])
    assert r_huge.status_code == 422, r_huge.text


def test_invalid_status_period_and_target_type_rejected(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow()
    later = now + timedelta(days=30)

    base = {
        "store_id": s1.id,
        "target_value": 5000.00,
        "start_date": now.isoformat(),
        "end_date": later.isoformat(),
    }

    # Invalid status on create -> 422
    r_status = client.post(
        "/api/v1/store-targets",
        json={**base, "target_type": "Sales", "period": "monthly", "status": "bogus_status"},
        headers=tenant["headers"],
    )
    assert r_status.status_code == 422, r_status.text

    # Invalid period -> 422
    r_period = client.post(
        "/api/v1/store-targets",
        json={**base, "target_type": "Sales", "period": "century"},
        headers=tenant["headers"],
    )
    assert r_period.status_code == 422, r_period.text

    # Invalid target type (symbols) -> 422
    r_ttype = client.post(
        "/api/v1/store-targets",
        json={**base, "target_type": "Sales@#$!", "period": "monthly"},
        headers=tenant["headers"],
    )
    assert r_ttype.status_code == 422, r_ttype.text


def test_overlap_on_put_and_patch(tenant, stores):
    s1, _ = stores
    t0 = datetime.utcnow()

    # Target 1: Month 1
    t1_resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Audit Overlap Target",
            "target_value": 10000.00,
            "period": "monthly",
            "start_date": t0.isoformat(),
            "end_date": (t0 + timedelta(days=30)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert t1_resp.status_code == 201
    target1_id = t1_resp.json()["id"]

    # Target 2: Month 2 (Non-overlapping)
    t2_resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Audit Overlap Target",
            "target_value": 15000.00,
            "period": "monthly",
            "start_date": (t0 + timedelta(days=31)).isoformat(),
            "end_date": (t0 + timedelta(days=60)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert t2_resp.status_code == 201
    target2_id = t2_resp.json()["id"]

    # PUT Target 2 to overlap with Target 1 -> 409 Conflict
    put_overlap = client.put(
        f"/api/v1/store-targets/{target2_id}",
        json={
            "start_date": (t0 + timedelta(days=15)).isoformat(),
            "end_date": (t0 + timedelta(days=45)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert put_overlap.status_code == 409, put_overlap.text
    assert "already exists" in put_overlap.text

    # PATCH Target 2 to overlap with Target 1 -> 409 Conflict
    patch_overlap = client.patch(
        f"/api/v1/store-targets/{target2_id}",
        json={
            "start_date": (t0 + timedelta(days=20)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert patch_overlap.status_code == 409, patch_overlap.text

    # Updating Target 2 without changing dates does NOT conflict with itself
    patch_self = client.patch(
        f"/api/v1/store-targets/{target2_id}",
        json={"target_value": 18000.00},
        headers=tenant["headers"],
    )
    assert patch_self.status_code == 200, patch_self.text
    assert float(patch_self.json()["target_value"]) == 18000.00

    # Case-insensitive overlap check ("audit overlap target" vs "Audit Overlap Target")
    case_overlap = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "audit overlap target",
            "target_value": 5000.00,
            "period": "monthly",
            "start_date": t0.isoformat(),
            "end_date": (t0 + timedelta(days=30)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert case_overlap.status_code == 409, case_overlap.text


def test_progress_with_zero_sales(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow() - timedelta(days=5)
    later = now + timedelta(days=25)

    r = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Zero Sales Target",
            "target_value": 50000.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert r.status_code == 201
    tid = r.json()["id"]

    prog = client.get(f"/api/v1/store-targets/{tid}/progress", headers=tenant["headers"]).json()
    assert float(prog["target_value"]) == 50000.00
    assert float(prog["current_value"]) == 0.00
    assert float(prog["achievement_percentage"]) == 0.0
    assert float(prog["remaining_value"]) == 50000.00
    assert prog["is_achieved"] is False


def test_progress_exceeding_100_percent(tenant, stores):
    s1, _ = stores
    now = datetime.utcnow() - timedelta(days=5)
    later = now + timedelta(days=25)

    r = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Overachieved Target",
            "target_value": 200.00,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert r.status_code == 201
    tid = r.json()["id"]

    # Insert sales totaling 300.00 (150% achievement)
    db = SessionLocal()
    try:
        s = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"SALE-OVER-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("300.00"),
            total_amount=Decimal("300.00"),
            payment_method="card",
            payment_status="paid",
            created_at=datetime.utcnow(),
        )
        db.add(s)
        db.commit()
    finally:
        db.close()

    prog = client.get(f"/api/v1/store-targets/{tid}/progress", headers=tenant["headers"]).json()
    assert float(prog["target_value"]) == 200.00
    assert float(prog["current_value"]) == 300.00
    assert float(prog["achievement_percentage"]) == 150.0
    assert float(prog["remaining_value"]) == 0.00
    assert prog["is_achieved"] is True


def test_progress_excludes_cancelled_and_out_of_range_sales(tenant, stores):
    s1, _ = stores
    t_start = datetime.utcnow() - timedelta(days=10)
    t_end = datetime.utcnow() + timedelta(days=10)

    r = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1.id,
            "target_type": "Filter Sales Target",
            "target_value": 1000.00,
            "period": "monthly",
            "start_date": t_start.isoformat(),
            "end_date": t_end.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert r.status_code == 201
    tid = r.json()["id"]

    db = SessionLocal()
    try:
        # 1. Valid paid sale in range -> 250.00
        s1_valid = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"S-VAL-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("250.00"),
            total_amount=Decimal("250.00"),
            payment_method="upi",
            payment_status="paid",
            created_at=datetime.utcnow(),
        )
        # 2. Cancelled sale in range -> 500.00 (MUST BE EXCLUDED)
        s2_cancelled = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"S-CAN-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            payment_method="cash",
            payment_status="cancelled",
            created_at=datetime.utcnow(),
        )
        # 3. Refunded sale in range -> 300.00 (MUST BE EXCLUDED)
        s3_refunded = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"S-REF-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("300.00"),
            total_amount=Decimal("300.00"),
            payment_method="card",
            payment_status="refunded",
            created_at=datetime.utcnow(),
        )
        # 4. Paid sale BEFORE start date -> 400.00 (MUST BE EXCLUDED)
        s4_before = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"S-BEF-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("400.00"),
            total_amount=Decimal("400.00"),
            payment_method="cash",
            payment_status="paid",
            created_at=t_start - timedelta(days=2),
        )
        # 5. Paid sale AFTER end date -> 600.00 (MUST BE EXCLUDED)
        s5_after = Sale(
            tenant_id=tenant["tenant_id"],
            store_id=s1.id,
            sale_number=f"S-AFT-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("600.00"),
            total_amount=Decimal("600.00"),
            payment_method="cash",
            payment_status="paid",
            created_at=t_end + timedelta(days=2),
        )
        db.add_all([s1_valid, s2_cancelled, s3_refunded, s4_before, s5_after])
        db.commit()
    finally:
        db.close()

    prog = client.get(f"/api/v1/store-targets/{tid}/progress", headers=tenant["headers"]).json()
    # ONLY s1_valid (250.00) should be included!
    assert float(prog["current_value"]) == 250.00
    assert float(prog["remaining_value"]) == 750.00
    assert float(prog["achievement_percentage"]) == 25.0
    assert prog["is_achieved"] is False


def test_pagination_and_filtering(tenant, stores):
    s1, _ = stores
    t0 = datetime.utcnow()

    # Create 3 targets
    names = ["Alpha Target", "Beta Target", "Gamma Target"]
    for i in range(3):
        res = client.post(
            "/api/v1/store-targets",
            json={
                "store_id": s1.id,
                "target_type": names[i],
                "target_value": 1000.00 * (i + 1),
                "period": "weekly" if i == 0 else "monthly",
                "start_date": (t0 + timedelta(days=i * 10)).isoformat(),
                "end_date": (t0 + timedelta(days=(i + 1) * 10)).isoformat(),
            },
            headers=tenant["headers"],
        )
        assert res.status_code == 201, res.text

    # 1. Filter by period=weekly
    r_weekly = client.get(f"/api/v1/store-targets?store_id={s1.id}&period=weekly", headers=tenant["headers"])
    assert r_weekly.status_code == 200
    assert all(t["period"] == "weekly" for t in r_weekly.json())

    # 2. Filter by status=active
    r_act = client.get(f"/api/v1/store-targets?store_id={s1.id}&status=active", headers=tenant["headers"])
    assert r_act.status_code == 200
    assert all(t["status"] == "active" for t in r_act.json())

    # 3. Pagination with skip=0&limit=1
    r_page1 = client.get(f"/api/v1/store-targets?store_id={s1.id}&skip=0&limit=1", headers=tenant["headers"])
    assert r_page1.status_code == 200
    assert len(r_page1.json()) == 1

    # 4. Pagination with page=1&page_size=2
    r_page = client.get(f"/api/v1/store-targets?store_id={s1.id}&page=1&page_size=2", headers=tenant["headers"])
    assert r_page.status_code == 200
    assert len(r_page.json()) <= 2


def test_auto_complete_expired_targets_lifecycle(tenant, stores):
    from app.services.store_target_service import StoreTargetService
    from app.tasks.store_target_tasks import process_expired_store_targets_task

    s1, _ = stores
    fixed_now = datetime(2026, 10, 15, 12, 0, 0)
    db = SessionLocal()

    try:
        # 1. Active target before end_date (ends in future -> should NOT expire)
        t_active_future = StoreTarget(
            store_id=s1.id,
            target_type="Future Target",
            target_value=Decimal("1000.00"),
            period="monthly",
            start_date=fixed_now - timedelta(days=5),
            end_date=fixed_now + timedelta(days=10),
            status="active",
        )
        # 2. Active target after end_date (ended in past -> MUST transition to 'completed')
        t_active_past = StoreTarget(
            store_id=s1.id,
            target_type="Expired Target",
            target_value=Decimal("2000.00"),
            period="monthly",
            start_date=fixed_now - timedelta(days=20),
            end_date=fixed_now - timedelta(days=2),
            status="active",
        )
        # 3. Already completed target (ended in past -> should remain 'completed')
        t_completed = StoreTarget(
            store_id=s1.id,
            target_type="Already Completed",
            target_value=Decimal("3000.00"),
            period="monthly",
            start_date=fixed_now - timedelta(days=25),
            end_date=fixed_now - timedelta(days=5),
            status="completed",
        )
        # 4. Cancelled target (ended in past -> should remain 'cancelled')
        t_cancelled = StoreTarget(
            store_id=s1.id,
            target_type="Cancelled Target",
            target_value=Decimal("4000.00"),
            period="monthly",
            start_date=fixed_now - timedelta(days=25),
            end_date=fixed_now - timedelta(days=5),
            status="cancelled",
        )
        # 5. Inactive target (ended in past -> should remain 'inactive')
        t_inactive = StoreTarget(
            store_id=s1.id,
            target_type="Inactive Target",
            target_value=Decimal("5000.00"),
            period="monthly",
            start_date=fixed_now - timedelta(days=25),
            end_date=fixed_now - timedelta(days=5),
            status="inactive",
        )

        db.add_all([t_active_future, t_active_past, t_completed, t_cancelled, t_inactive])
        db.commit()
        db.refresh(t_active_future)
        db.refresh(t_active_past)
        db.refresh(t_completed)
        db.refresh(t_cancelled)
        db.refresh(t_inactive)

        # First execution: should only transition t_active_past for this store
        summary1 = StoreTargetService.auto_complete_expired_targets(db, now=fixed_now, store_id=s1.id)
        assert summary1["transitioned_count"] == 1
        assert summary1["target_ids"] == [t_active_past.id]

        db.refresh(t_active_future)
        db.refresh(t_active_past)
        db.refresh(t_completed)
        db.refresh(t_cancelled)
        db.refresh(t_inactive)

        assert t_active_future.status == "active"
        assert t_active_past.status == "completed"
        assert t_completed.status == "completed"
        assert t_cancelled.status == "cancelled"
        assert t_inactive.status == "inactive"

        # Repeated execution: idempotent, 0 transitioned
        summary2 = StoreTargetService.auto_complete_expired_targets(db, now=fixed_now, store_id=s1.id)
        assert summary2["transitioned_count"] == 0
        assert summary2["target_ids"] == []

        # Celery task wrapper execution verification
        task_res = process_expired_store_targets_task()
        assert task_res["status"] == "success"
        assert "transitioned_count" in task_res

    finally:
        db.close()


def test_concurrent_overlapping_target_creation(tenant, stores):
    from concurrent.futures import ThreadPoolExecutor

    s1, _ = stores
    t_start = datetime.utcnow() + timedelta(days=5)
    t_end = t_start + timedelta(days=20)

    payload = {
        "store_id": s1.id,
        "target_type": "Simultaneous Target",
        "target_value": 75000.00,
        "period": "monthly",
        "start_date": t_start.isoformat(),
        "end_date": t_end.isoformat(),
    }

    def attempt_create():
        return client.post("/api/v1/store-targets", json=payload, headers=tenant["headers"])

    # Launch two concurrent attempts
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_create)
        f2 = executor.submit(attempt_create)
        r1 = f1.result()
        r2 = f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    # Exactly one must succeed (201) and the second must be rejected as conflict (409)
    assert statuses == [201, 409], f"Unexpected statuses: {statuses}, r1={r1.text}, r2={r2.text}"



