import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_login(unique_slug):
    email = f"owner-{unique_slug}@testcorp.com"
    register_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Test Corp",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Test Owner",
            "password": "testpass123",
        },
    )
    assert register_resp.status_code == 200

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_register_with_store_owner_aliases(unique_slug):
    """Verify registration accepts Store Owner terminology (store_name, owner_name, owner_email)."""
    email = f"owner-{unique_slug}-so@example.com"
    payload = {
        "store_name": f"Store {unique_slug}",
        "domain": f"so-{unique_slug}",
        "owner_email": email,
        "owner_name": "Store Owner Name",
        "password": "Password@123!",
        "owner_phone": "9876543210",
    }
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 200
    assert r.json()["message"] == "Tenant registered"
    assert "user_id" in r.json()
    assert "tenant_id" in r.json()


def test_password_recovery_and_change_flow(unique_slug):
    """Verify forgot-password -> verify-otp -> reset-password -> change-password flow."""
    email = f"pwd-{unique_slug}@example.com"
    initial_pass = "InitialPass@123!"

    # 1. Register user
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Pwd Mart {unique_slug}",
            "domain": f"pwd-{unique_slug}",
            "owner_email": email,
            "owner_name": "Pwd User",
            "password": initial_pass,
        },
    )
    assert reg.status_code == 200

    # 2. Forgot password -> receives OTP
    fp_r = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert fp_r.status_code == 200
    otp = fp_r.json()["otp"]
    assert len(otp) == 6

    # 3. Verify OTP -> receives reset_token
    vo_r = client.post("/api/v1/auth/verify-otp", json={"email": email, "otp": otp})
    assert vo_r.status_code == 200
    reset_token = vo_r.json()["reset_token"]
    assert reset_token

    # 4. Reset password with reset_token
    new_pass = "ResetPassword@123!"
    rp_r = client.post("/api/v1/auth/reset-password", json={"token": reset_token, "new_password": new_pass})
    assert rp_r.status_code == 200
    assert rp_r.json()["success"] is True

    # 5. Login with new password
    login_r = client.post("/api/v1/auth/login", json={"email": email, "password": new_pass})
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 6. Change password with active session
    final_pass = "FinalChangedPassword@123!"
    cp_r = client.post(
        "/api/v1/auth/change-password",
        json={
            "old_password": new_pass,
            "new_password": final_pass,
            "confirm_password": final_pass,
        },
        headers=headers,
    )
    assert cp_r.status_code == 200
    assert cp_r.json()["success"] is True


def test_users_crud_and_profile_flow(unique_slug):
    """Verify /api/v1/users endpoints: roles, create, list, me, update, activate/deactivate, delete."""
    admin_email = f"admin-{unique_slug}@example.com"
    admin_pass = "AdminPass@123!"

    # Register admin with enterprise plan (allows multiple users)
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Users Test Store {unique_slug}",
            "domain": f"usr-{unique_slug}",
            "owner_email": admin_email,
            "owner_name": "Admin Owner",
            "password": admin_pass,
            "plan_code": "enterprise",
        },
    )
    assert reg.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": admin_email, "password": admin_pass})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /api/v1/users/roles
    roles_r = client.get("/api/v1/users/roles", headers=headers)
    assert roles_r.status_code == 200
    roles = roles_r.json()
    assert len(roles) >= 1
    # Pick a non-admin role if available, or admin
    cashier_role = next((r for r in roles if r["name"] == "cashier"), roles[0])

    # 2. GET /api/v1/users/me
    me_r = client.get("/api/v1/users/me", headers=headers)
    assert me_r.status_code == 200
    assert me_r.json()["email"] == admin_email

    # 3. PUT & PATCH /api/v1/users/me
    put_me = client.put("/api/v1/users/me", json={"full_name": "Updated Admin Owner"}, headers=headers)
    assert put_me.status_code == 200
    assert put_me.json()["full_name"] == "Updated Admin Owner"

    patch_me = client.patch("/api/v1/users/me", json={"phone": "9811223344"}, headers=headers)
    assert patch_me.status_code == 200
    assert patch_me.json()["phone"] == "9811223344"

    # 4. POST /api/v1/users (Create user)
    staff_email = f"staff-{unique_slug}@example.com"
    staff_payload = {
        "email": staff_email,
        "full_name": "Staff Cashier",
        "phone": "9822334455",
        "role_id": cashier_role["id"],
        "password": "StaffPassword@123!",
    }
    create_r = client.post("/api/v1/users", json=staff_payload, headers=headers)
    assert create_r.status_code == 201
    staff_user = create_r.json()
    staff_id = staff_user["id"]
    assert staff_user["email"] == staff_email
    assert staff_user["is_active"] is True

    # 5. GET /api/v1/users (List users)
    list_r = client.get("/api/v1/users", headers=headers)
    assert list_r.status_code == 200
    users = list_r.json()
    assert any(u["id"] == staff_id for u in users)

    # 6. GET /api/v1/users/{user_id}
    get_u = client.get(f"/api/v1/users/{staff_id}", headers=headers)
    assert get_u.status_code == 200
    assert get_u.json()["id"] == staff_id

    # 7. PUT & PATCH /api/v1/users/{user_id}
    update_r = client.put(f"/api/v1/users/{staff_id}", json={"full_name": "Renamed Staff"}, headers=headers)
    assert update_r.status_code == 200
    assert update_r.json()["full_name"] == "Renamed Staff"

    patch_u = client.patch(f"/api/v1/users/{staff_id}", json={"phone": "9899887766"}, headers=headers)
    assert patch_u.status_code == 200
    assert patch_u.json()["phone"] == "9899887766"

    # 8. PATCH /api/v1/users/{user_id}/deactivate
    deact_r = client.patch(f"/api/v1/users/{staff_id}/deactivate", headers=headers)
    assert deact_r.status_code == 200
    assert deact_r.json()["is_active"] is False

    # 9. PATCH /api/v1/users/{user_id}/activate
    act_r = client.patch(f"/api/v1/users/{staff_id}/activate", headers=headers)
    assert act_r.status_code == 200
    assert act_r.json()["is_active"] is True

    # 10. DELETE /api/v1/users/{user_id}
    del_r = client.delete(f"/api/v1/users/{staff_id}", headers=headers)
    assert del_r.status_code == 204

    # Deleted user should not be accessible
    assert client.get(f"/api/v1/users/{staff_id}", headers=headers).status_code == 404
