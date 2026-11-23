import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.sale import Sale
from app.models.store import Store
from app.models.store_target import StoreTarget
from app.schemas.store_target import (
    StoreTargetCreate,
    StoreTargetUpdate,
    StoreTargetLeaderboardItem,
)

client = TestClient(app)


def create_tenant_and_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {slug}",
            "domain": slug,
            "owner_email": email,
            "owner_name": f"Admin {prefix}",
            "password": "Password123!",
            "plan_code": "enterprise",
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
    }


def create_store(headers: dict, name: str = "Test Store Branch"):
    store_code = f"STR-{uuid.uuid4().hex[:4].upper()}"
    store_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": name,
            "code": store_code,
            "address": "123 High Street Commercial Area",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "phone": "9876543210",
        },
        headers=headers,
    )
    assert store_resp.status_code == 201, store_resp.text
    return store_resp.json()


# ==============================================================================
# Issue 1: Store Performance Leaderboard API – Achievement Percentage Calculation
# ==============================================================================

def test_leaderboard_achievement_percentage_calculation_and_validation():
    tenant = create_tenant_and_admin("lb-pct")
    headers = tenant["headers"]
    tenant_id = tenant["tenant_id"]

    store = create_store(headers, "Leaderboard Store Branch")
    store_id = store["id"]

    now = datetime.utcnow()
    later = now + timedelta(days=20)

    # Create target with target_value = 1.00
    target_resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store_id,
            "target_type": "Sales Target",
            "target_value": "1.00",
            "period": "daily",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert target_resp.status_code == 201, target_resp.text
    target_id = target_resp.json()["id"]

    # Record sale with total_amount = 580.00
    db = SessionLocal()
    try:
        sale = Sale(
            tenant_id=tenant_id,
            store_id=store_id,
            sale_number=f"SAL-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("580.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("580.00"),
            payment_method="cash",
            payment_status="completed",
            created_at=now,
        )
        db.add(sale)
        db.commit()
    finally:
        db.close()

    # Call leaderboard API
    lb_resp = client.get("/api/v1/store-targets/leaderboard", headers=headers)
    assert lb_resp.status_code == 200, lb_resp.text
    lb_data = lb_resp.json()

    # Find the target item in leaderboard
    matched_items = [item for item in lb_data["leaderboard"] if item["target_id"] == target_id]
    assert len(matched_items) == 1
    item = matched_items[0]

    assert float(item["target_value"]) == 1.0
    assert float(item["current_value"]) == 580.0
    # Expected formula: achievement_percentage = (current_value / target_value) * 100
    # (580.0 / 1.0) * 100 = 58000.0
    assert item["achievement_percentage"] == 58000.0
    assert item["is_achieved"] is True


def test_schema_level_achievement_percentage_validation():
    # Test valid calculation and recalculation
    item = StoreTargetLeaderboardItem(
        rank=1,
        target_id=1,
        store_id=1,
        store_name="Branch Store",
        target_type="Sales Target",
        target_value=Decimal("1.00"),
        current_value=Decimal("580.00"),
        achievement_percentage=0.0,
        remaining_value=Decimal("0.00"),
        period="daily",
        is_achieved=True,
        status="active",
    )
    assert item.achievement_percentage == 58000.0

    # Test when target_value is 0 or negative
    item_zero = StoreTargetLeaderboardItem(
        rank=1,
        target_id=2,
        store_id=1,
        store_name="Branch Store",
        target_type="Sales Target",
        target_value=Decimal("0.00"),
        current_value=Decimal("580.00"),
        achievement_percentage=100.0,
        remaining_value=Decimal("0.00"),
        period="daily",
        is_achieved=True,
        status="active",
    )
    assert item_zero.achievement_percentage == 0.0


# ==============================================================================
# Issue 2: Update Store Target API – Missing Target Type Validation
# ==============================================================================

def test_update_store_target_rejects_null_string_and_none():
    tenant = create_tenant_and_admin("upd-tgt")
    headers = tenant["headers"]

    store = create_store(headers, "Update Store Target Branch")
    store_id = store["id"]

    now = datetime.utcnow()
    later = now + timedelta(days=25)

    # 1. Create a valid target
    create_resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store_id,
            "target_type": "Sales Target",
            "target_value": "50000.00",
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    target_id = create_resp.json()["id"]

    # 2. PUT with target_type = "null" as string -> must be rejected 422
    put_null_str_resp = client.put(
        f"/api/v1/store-targets/{target_id}",
        json={
            "target_type": "null",
            "target_value": 60000,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert put_null_str_resp.status_code == 422, put_null_str_resp.text

    # 3. PUT with target_type = null (actual None/null) -> must be rejected 422
    put_none_resp = client.put(
        f"/api/v1/store-targets/{target_id}",
        json={
            "target_type": None,
            "target_value": 60000,
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert put_none_resp.status_code == 422, put_none_resp.text

    # 4. PATCH with target_type = "null" -> must be rejected 422
    patch_null_str_resp = client.patch(
        f"/api/v1/store-targets/{target_id}",
        json={"target_type": "null"},
        headers=headers,
    )
    assert patch_null_str_resp.status_code == 422, patch_null_str_resp.text

    # 5. PATCH with target_type = null -> must be rejected 422
    patch_none_resp = client.patch(
        f"/api/v1/store-targets/{target_id}",
        json={"target_type": None},
        headers=headers,
    )
    assert patch_none_resp.status_code == 422, patch_none_resp.text

    # 6. PUT with unsupported target_type -> must be rejected 422
    put_invalid_resp = client.put(
        f"/api/v1/store-targets/{target_id}",
        json={"target_type": "Arbitrary Unsupported Type"},
        headers=headers,
    )
    assert put_invalid_resp.status_code == 422, put_invalid_resp.text

    # 7. PUT with valid target_type (e.g. "Revenue Target") -> must succeed 200
    put_valid_resp = client.put(
        f"/api/v1/store-targets/{target_id}",
        json={"target_type": "Revenue Target"},
        headers=headers,
    )
    assert put_valid_resp.status_code == 200, put_valid_resp.text
    assert put_valid_resp.json()["target_type"] == "Revenue Target"


def test_create_store_target_also_rejects_null_string_and_none():
    tenant = create_tenant_and_admin("crt-tgt")
    headers = tenant["headers"]
    store = create_store(headers, "Create Store Target Branch")

    now = datetime.utcnow()
    later = now + timedelta(days=25)

    # 1. target_type = "null"
    resp_null_str = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "null",
            "target_value": "50000.00",
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert resp_null_str.status_code == 422, resp_null_str.text

    # 2. target_type = null
    resp_none = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": None,
            "target_value": "50000.00",
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert resp_none.status_code == 422, resp_none.text

