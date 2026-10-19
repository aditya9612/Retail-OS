import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.order import Order
from app.models.sale import Sale
from app.models.store import Store

client = TestClient(app)


def create_tenant(prefix: str):
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
        "headers": headers,
    }


def test_leaderboard_and_summary_flow():
    tenant = create_tenant("tgtlead")
    headers = tenant["headers"]
    tenant_id = tenant["tenant_id"]

    # 1. Create two stores
    db = SessionLocal()
    try:
        s1 = Store(name="Dadar Branch", code=f"DAD-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        s2 = Store(name="Pune Branch", code=f"PUN-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        s1_id = s1.id
        s2_id = s2.id
    finally:
        db.close()

    now = datetime.utcnow()
    later = now + timedelta(days=30)

    # 2. Create Target for Store 1: ₹100,000 monthly Sales Target
    t1_resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s1_id,
            "target_type": "Sales Target",
            "target_value": "100000.00",
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert t1_resp.status_code == 201, t1_resp.text
    t1 = t1_resp.json()
    assert t1["store_name"] == "Dadar Branch"

    # 3. Create Target for Store 2: ₹200,000 monthly Sales Target
    t2_resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": s2_id,
            "target_type": "Sales Target",
            "target_value": "200000.00",
            "period": "monthly",
            "start_date": now.isoformat(),
            "end_date": later.isoformat(),
        },
        headers=headers,
    )
    assert t2_resp.status_code == 201, t2_resp.text
    t2 = t2_resp.json()
    assert t2["store_name"] == "Pune Branch"

    # 4. Add sales:
    # Store 1 gets ₹110,000 sales via Sale table (110% achievement!)
    # Store 2 gets ₹50,000 sales via Order table (25% achievement!)
    db = SessionLocal()
    try:
        sale1 = Sale(
            tenant_id=tenant_id,
            store_id=s1_id,
            sale_number=f"SAL-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("110000.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("110000.00"),
            payment_method="cash",
            payment_status="completed",
            created_at=now + timedelta(days=1),
        )
        order2 = Order(
            tenant_id=tenant_id,
            store_id=s2_id,
            order_number=f"ORD-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal("50000.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("50000.00"),
            status="completed",
            payment_status="paid",
            created_at=now + timedelta(days=1),
        )
        db.add_all([sale1, order2])
        db.commit()
    finally:
        db.close()

    # 5. Check Progress API for both targets includes store_name
    p1 = client.get(f"/api/v1/store-targets/{t1['id']}/progress", headers=headers).json()
    assert p1["store_name"] == "Dadar Branch"
    assert p1["achievement_percentage"] == 110.0
    assert p1["is_achieved"] is True

    p2 = client.get(f"/api/v1/store-targets/{t2['id']}/progress", headers=headers).json()
    assert p2["store_name"] == "Pune Branch"
    assert p2["achievement_percentage"] == 25.0
    assert p2["is_achieved"] is False

    # 6. Test GET /api/v1/store-targets/leaderboard
    lb_resp = client.get("/api/v1/store-targets/leaderboard", headers=headers)
    assert lb_resp.status_code == 200, lb_resp.text
    lb_data = lb_resp.json()
    assert lb_data["total_ranked"] >= 2
    leaderboard = lb_data["leaderboard"]

    # Rank 1 must be Dadar Branch with 110%
    assert leaderboard[0]["rank"] == 1
    assert leaderboard[0]["store_name"] == "Dadar Branch"
    assert leaderboard[0]["achievement_percentage"] == 110.0
    assert leaderboard[0]["is_achieved"] is True

    # Rank 2 must be Pune Branch with 25%
    assert leaderboard[1]["rank"] == 2
    assert leaderboard[1]["store_name"] == "Pune Branch"
    assert leaderboard[1]["achievement_percentage"] == 25.0
    assert leaderboard[1]["is_achieved"] is False

    # Filter leaderboard by period
    lb_monthly = client.get("/api/v1/store-targets/leaderboard?period=monthly", headers=headers).json()
    assert lb_monthly["total_ranked"] >= 2

    # 7. Test GET /api/v1/store-targets/summary
    sum_resp = client.get("/api/v1/store-targets/summary", headers=headers)
    assert sum_resp.status_code == 200, sum_resp.text
    summary = sum_resp.json()
    assert summary["total_targets"] >= 2
    assert summary["total_stores_with_targets"] >= 2
    assert float(summary["total_target_value"]) >= 300000.00
    assert float(summary["total_current_value"]) >= 160000.00
    assert summary["achieved_targets_count"] >= 1
    assert summary["lagging_targets_count"] >= 1
    assert summary["overall_achievement_percentage"] > 0
