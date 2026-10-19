import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_user_with_role_having_spaces():
    unique_slug = uuid.uuid4().hex[:8]
    owner_email = f"owner-sp-{unique_slug}@retailstore.com"

    # 1. Register tenant
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"SpaceMart {unique_slug}",
            "domain": f"sp-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": "9812400001",
        },
    )
    assert reg_res.status_code == 200
    tenant_id = reg_res.json()["tenant_id"]

    # 2. Login as Owner
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200
    owner_token = login_res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 3. Create a custom role with spaces: "store area manager"
    create_role_res = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={
            "name": "store area manager",
            "permissions": ["products:read", "inventory:read"],
        },
    )
    assert create_role_res.status_code == 201
    created_role = create_role_res.json()
    assert created_role["name"] == "store area manager"
    role_id = created_role["id"]

    # Ensure quota exists
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.saas_billing import SaaSSubscription
    from app.models.saas_plan_entitlement import SaaSPlanEntitlement, EntitlementDimension

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.domain == f"sp-{unique_slug}").first()
        sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == tenant.id).first()
        if sub and sub.plan_id:
            ent = db.query(SaaSPlanEntitlement).filter(
                SaaSPlanEntitlement.plan_id == sub.plan_id,
                SaaSPlanEntitlement.dimension == EntitlementDimension.USERS,
            ).first()
            if not ent:
                db.add(
                    SaaSPlanEntitlement(
                        plan_id=sub.plan_id,
                        dimension=EntitlementDimension.USERS,
                        is_unlimited=True,
                    )
                )
                db.commit()
    finally:
        db.close()

    # 4. Create user with role name "store area manager" using multipart/form-data
    user1_email = f"sam-{unique_slug}@retailstore.com"
    res1 = client.post(
        "/api/v1/users",
        headers=owner_headers,
        data={
            "email": user1_email,
            "full_name": "Amit Sharma",
            "password": "SecurePass@123",
            "phone": "9812400002",
            "role": "store area manager",
            "pan_number": "ABCDE1234F",
            "addhar_number": "987654321012",
        },
    )
    assert res1.status_code == 201, res1.text
    user1 = res1.json()
    assert user1["role"]["name"] == "store area manager"
    assert user1["role_id"] == role_id

    # 5. Create user with role_id instead of role name (role sending empty string)
    user2_email = f"sam2-{unique_slug}@retailstore.com"
    res2 = client.post(
        "/api/v1/users",
        headers=owner_headers,
        data={
            "email": user2_email,
            "full_name": "Sumit Sharma",
            "password": "SecurePass@123",
            "phone": "9812400003",
            "role_id": str(role_id),
            "role": "",
        },
    )
    assert res2.status_code == 201, res2.text
    user2 = res2.json()
    assert user2["role"]["name"] == "store area manager"
    assert user2["role_id"] == role_id
