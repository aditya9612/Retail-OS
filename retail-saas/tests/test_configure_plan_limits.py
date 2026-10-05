import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.super_admin import SuperAdmin
from app.core.security import get_password_hash, create_super_admin_access_token

client = TestClient(app)


@pytest.fixture
def super_admin_auth():
    db = SessionLocal()
    try:
        uid = uuid.uuid4().hex[:6]
        admin = SuperAdmin(
            email=f"sa_{uid}@example.com",
            full_name=f"Super Admin {uid}",
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
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def test_configure_plan_limits_by_id(super_admin_auth):
    # Configure limits for plan 1 (basic) with specific numbers
    resp = client.put(
        "/api/v1/super-admins/saas-plans/1/configure-limits",
        headers=super_admin_auth,
        json={
            "users": 15,
            "stores": 3,
            "products": 5000,
            "monthly_orders": 2000,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["plan_id"] == 1
    
    limits_dict = {item["dimension"]: item for item in data["limits"]}
    assert limits_dict["users"]["value"] == 15
    assert limits_dict["users"]["is_unlimited"] is False
    assert limits_dict["stores"]["value"] == 3
    assert limits_dict["products"]["value"] == 5000
    assert limits_dict["monthly_orders"]["value"] == 2000


def test_configure_plan_limits_unlimited_by_code(super_admin_auth):
    # Configure enterprise plan to be completely unlimited
    resp = client.put(
        "/api/v1/super-admins/saas-plans/enterprise/configure-limits",
        headers=super_admin_auth,
        json={
            "users": None,
            "is_users_unlimited": True,
            "stores": None,
            "is_stores_unlimited": True,
            "products": None,
            "is_products_unlimited": True,
            "monthly_orders": None,
            "is_monthly_orders_unlimited": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["plan_code"] == "enterprise"

    limits_dict = {item["dimension"]: item for item in data["limits"]}
    assert limits_dict["users"]["is_unlimited"] is True
    assert limits_dict["users"]["value"] is None
    assert limits_dict["stores"]["is_unlimited"] is True
    assert limits_dict["products"]["is_unlimited"] is True
    assert limits_dict["monthly_orders"]["is_unlimited"] is True


def test_configure_plan_limits_by_body_endpoint(super_admin_auth):
    resp = client.post(
        "/api/v1/super-admins/saas-plans/configure-limits",
        headers=super_admin_auth,
        json={
            "plan_code": "pro",
            "users": 30,
            "stores": 7,
            "products": 15000,
            "monthly_orders": 8000,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["plan_code"] == "pro"

    limits_dict = {item["dimension"]: item for item in data["limits"]}
    assert limits_dict["users"]["value"] == 30
    assert limits_dict["stores"]["value"] == 7

