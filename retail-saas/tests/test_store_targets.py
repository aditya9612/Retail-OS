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

