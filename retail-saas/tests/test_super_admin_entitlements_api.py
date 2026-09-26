from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import (
    blacklist_token,
    create_access_token,
    create_super_admin_access_token,
    get_password_hash,
)
from app.main import app
from app.models.saas_billing import SaaSPlan
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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


@pytest.fixture
def inactive_super_admin(db: Session):
    uid = uuid.uuid4().hex[:6]
    admin = SuperAdmin(
        email=f"inact_{uid}@example.com",
        full_name=f"Inactive {uid}",
        hashed_password=get_password_hash("AdminPass123!"),
        is_active=False,
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


@pytest.fixture
def test_plan(db: Session):
    uid = uuid.uuid4().hex[:6]
    plan = SaaSPlan(
        name=f"Test Plan {uid}",
        code=f"tp_{uid}",
        price=Decimal("999.00"),
        currency="INR",
        billing_interval="monthly",
        trial_days=14,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


class TestSuperAdminEntitlementsApi:
    def test_create_limited_entitlement_success(self, active_super_admin, test_plan, db: Session):
        headers = active_super_admin["headers"]
        payload = {
            "dimension": EntitlementDimension.USERS,
            "value": 25,
            "is_unlimited": False,
        }
        r = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json=payload,
            headers=headers,
        )
        assert r.status_code == 201, f"Create entitlement failed: {r.text}"
        data = r.json()
        assert data["plan_id"] == test_plan.id
        assert data["dimension"] == "users"
        assert data["value"] == 25
        assert data["is_unlimited"] is False

    def test_create_unlimited_entitlement_success(self, active_super_admin, test_plan, db: Session):
        headers = active_super_admin["headers"]
        payload = {
            "dimension": EntitlementDimension.PRODUCTS,
            "value": None,
            "is_unlimited": True,
        }
        r = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json=payload,
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["plan_id"] == test_plan.id
        assert data["dimension"] == "products"
        assert data["value"] is None
        assert data["is_unlimited"] is True

    def test_list_plan_entitlements(self, active_super_admin, test_plan, db: Session):
        headers = active_super_admin["headers"]
        # Create two entitlements
        client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": EntitlementDimension.USERS, "value": 10, "is_unlimited": False},
            headers=headers,
        )
        client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": EntitlementDimension.STORES, "value": 2, "is_unlimited": False},
            headers=headers,
        )

        r = client.get(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["plan_id"] == test_plan.id
        assert data["total"] == 2
        dims = [item["dimension"] for item in data["items"]]
        assert "users" in dims
        assert "stores" in dims

    def test_update_plan_entitlement(self, active_super_admin, test_plan, db: Session):
        headers = active_super_admin["headers"]
        # Create limited users
        client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": EntitlementDimension.USERS, "value": 10, "is_unlimited": False},
            headers=headers,
        )

        # Update to unlimited
        r = client.put(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements/users",
            json={"is_unlimited": True, "value": None},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["is_unlimited"] is True
        assert data["value"] is None

        # Update back to limited with new value
        r2 = client.put(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements/users",
            json={"is_unlimited": False, "value": 50},
            headers=headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["is_unlimited"] is False
        assert data2["value"] == 50

    def test_delete_plan_entitlement(self, active_super_admin, test_plan, db: Session):
        headers = active_super_admin["headers"]
        client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": EntitlementDimension.STORES, "value": 3, "is_unlimited": False},
            headers=headers,
        )

        r = client.delete(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements/stores",
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Verify deleted
        list_r = client.get(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            headers=headers,
        )
        assert list_r.json()["total"] == 0

    def test_duplicate_plan_dimension_rejected(self, active_super_admin, test_plan):
        headers = active_super_admin["headers"]
        client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": EntitlementDimension.USERS, "value": 10, "is_unlimited": False},
            headers=headers,
        )
        # Attempt to create duplicate
        r = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": EntitlementDimension.USERS, "value": 20, "is_unlimited": False},
            headers=headers,
        )
        assert r.status_code == 409
        assert "already exists" in str(r.json()).lower()

    def test_nonexistent_plan_returns_404(self, active_super_admin):
        headers = active_super_admin["headers"]
        r = client.get(
            "/api/v1/super-admins/saas-plans/999999/entitlements",
            headers=headers,
        )
        assert r.status_code == 404

        r2 = client.post(
            "/api/v1/super-admins/saas-plans/999999/entitlements",
            json={"dimension": "users", "value": 10, "is_unlimited": False},
            headers=headers,
        )
        assert r2.status_code == 404

    def test_invalid_dimension_rejected(self, active_super_admin, test_plan):
        headers = active_super_admin["headers"]
        r = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": "invalid_dimension", "value": 10, "is_unlimited": False},
            headers=headers,
        )
        assert r.status_code in (400, 422)

    def test_limited_without_value_rejected(self, active_super_admin, test_plan):
        headers = active_super_admin["headers"]
        r = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": "users", "value": None, "is_unlimited": False},
            headers=headers,
        )
        assert r.status_code in (400, 422)

    def test_negative_value_rejected(self, active_super_admin, test_plan):
        headers = active_super_admin["headers"]
        r = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": "users", "value": -5, "is_unlimited": False},
            headers=headers,
        )
        assert r.status_code in (400, 422)

    def test_anonymous_rejected(self, test_plan):
        r = client.get(f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements")
        assert r.status_code == 401

        r2 = client.post(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            json={"dimension": "users", "value": 10, "is_unlimited": False},
        )
        assert r2.status_code == 401

    def test_tenant_jwt_rejected(self, test_plan, db: Session):
        # Create regular tenant user token
        tenant_user_token = create_access_token({
            "sub": "test@example.com",
            "user_id": 1,
            "tenant_id": 1,
            "role": "admin",
        })
        headers = {"Authorization": f"Bearer {tenant_user_token}"}
        r = client.get(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            headers=headers,
        )
        assert r.status_code in (401, 403)

    def test_inactive_super_admin_rejected(self, inactive_super_admin, test_plan):
        headers = inactive_super_admin["headers"]
        r = client.get(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            headers=headers,
        )
        assert r.status_code in (401, 403)

    def test_blacklisted_super_admin_token_rejected(self, active_super_admin, test_plan):
        token = active_super_admin["token"]
        headers = active_super_admin["headers"]
        # Blacklist the token in Redis
        blacklist_token(token)

        r = client.get(
            f"/api/v1/super-admins/saas-plans/{test_plan.id}/entitlements",
            headers=headers,
        )
        assert r.status_code == 401
