import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_users_module_enhancements_flow():
    unique_slug = uuid.uuid4().hex[:8]
    owner_email = f"owner-{unique_slug}@retailstore.com"

    # 1. Register tenant
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"EnhanceMart {unique_slug}",
            "domain": f"enh-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": "9812300001",
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

    # Get Owner ID from /users/me
    owner_profile_res = client.get("/api/v1/users/me", headers=owner_headers)
    assert owner_profile_res.status_code == 200
    owner_id = owner_profile_res.json()["id"]
    assert owner_profile_res.json()["email"] == owner_email

    # 3. Create a Cashier using JSON (Dual-Mode JSON support)
    cashier_email = f"cashier-{unique_slug}@retailstore.com"
    create_cashier_res = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": cashier_email,
            "full_name": "Ramesh Cashier",
            "password": "Password@123!",
            "role": "cashier",
            "phone": "9812300002",
        },
    )
    assert create_cashier_res.status_code == 201
    cashier_user = create_cashier_res.json()
    cashier_id = cashier_user["id"]
    assert cashier_user["role"]["name"] == "cashier"

    # 4. Login as Cashier (who does NOT have users:read or users:write)
    cashier_login_res = client.post(
        "/api/v1/auth/login",
        json={"email": cashier_email, "password": "Password@123!"},
    )
    assert cashier_login_res.status_code == 200
    cashier_token = cashier_login_res.json()["access_token"]
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    # 5. Cashier accesses /api/v1/users/me -> MUST BE 200 (not 403 Forbidden!)
    cashier_me_res = client.get("/api/v1/users/me", headers=cashier_headers)
    assert cashier_me_res.status_code == 200
    assert cashier_me_res.json()["id"] == cashier_id
    assert cashier_me_res.json()["email"] == cashier_email

    # 6. Cashier updates own profile -> MUST BE 200
    update_me_res = client.put(
        "/api/v1/users/me",
        headers=cashier_headers,
        json={"full_name": "Ramesh Kumar Cashier"},
    )
    assert update_me_res.status_code == 200
    assert update_me_res.json()["full_name"] == "Ramesh Kumar Cashier"

    # Cashier cannot access other users -> 403
    forbidden_list = client.get("/api/v1/users", headers=cashier_headers)
    assert forbidden_list.status_code == 403

    # 7. Protect Owner from deactivation:
    # Attempting to deactivate Store Owner -> MUST FAIL with 409
    deactivate_owner_res = client.patch(
        f"/api/v1/users/{owner_id}/deactivate",
        headers=owner_headers,
    )
    # Could be "cannot deactivate your own account" or "Store Owner account cannot be deactivated"
    assert deactivate_owner_res.status_code == 409

    # 8. Attempting to deactivate Owner via PUT /users/{owner_id} with is_active=false -> 409
    put_deactivate_owner = client.put(
        f"/api/v1/users/{owner_id}",
        headers=owner_headers,
        json={"is_active": False},
    )
    assert put_deactivate_owner.status_code == 409

    # 9. Attempting to delete Store Owner -> MUST FAIL with 409
    delete_owner_res = client.delete(
        f"/api/v1/users/{owner_id}",
        headers=owner_headers,
    )
    assert delete_owner_res.status_code == 409
    assert "cannot delete" in delete_owner_res.text.lower() or "owner" in delete_owner_res.text.lower()

