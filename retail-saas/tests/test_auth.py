import random
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _random_phone() -> str:
    while True:
        p = f"{random.choice('6789')}{random.randint(100000000, 999999999)}"
        if p != "9876543210":
            return p


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
        "owner_phone": _random_phone(),
    }
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 200
    assert r.json()["message"] == "Tenant registered"
    assert "user_id" in r.json()
    assert "tenant_id" in r.json()


def test_password_recovery_and_change_flow(unique_slug, monkeypatch):
    """Verify forgot-password -> verify-otp -> reset-password -> change-password flow."""
    email = f"pwd-{unique_slug}@example.com"
    initial_pass = "InitialPass@123!"

    # Mock OTP generator so we know the expected OTP in test without exposing it in API response
    monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)

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

    # 2. Forgot password -> receives success message, OTP is NOT exposed
    fp_r = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert fp_r.status_code == 200
    assert "otp" not in fp_r.json()
    assert fp_r.json()["message"] == "OTP sent successfully."

    # 3. Verify OTP -> receives reset_token
    vo_r = client.post("/api/v1/auth/verify-otp", json={"email": email, "otp": "123456"})
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

    # 1. GET /api/v1/roles
    roles_r = client.get("/api/v1/roles", headers=headers)
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

    phone_me = _random_phone()
    patch_me = client.patch("/api/v1/users/me", json={"phone": phone_me}, headers=headers)
    assert patch_me.status_code == 200
    assert patch_me.json()["phone"] == phone_me

    # 4. POST /api/v1/users (Create user)
    staff_email = f"staff-{unique_slug}@example.com"
    phone_staff = _random_phone()
    staff_payload = {
        "email": staff_email,
        "full_name": "Staff Cashier",
        "phone": phone_staff,
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

    phone_staff_upd = _random_phone()
    patch_u = client.patch(f"/api/v1/users/{staff_id}", json={"phone": phone_staff_upd}, headers=headers)
    assert patch_u.status_code == 200
    assert patch_u.json()["phone"] == phone_staff_upd

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


def test_logout_revokes_access_token(unique_slug):
    """Verify that logging out blacklists the current access token."""
    email = f"logout-{unique_slug}@example.com"
    pwd = "LogoutPass@123!"

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Logout Store {unique_slug}",
            "domain": f"logout-{unique_slug}",
            "owner_email": email,
            "owner_name": "Logout User",
            "password": pwd,
        },
    )
    assert reg.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Token works initially
    me_resp = client.get("/api/v1/users/me", headers=headers)
    assert me_resp.status_code == 200

    # Logout
    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Token is now revoked
    subsequent_resp = client.get("/api/v1/users/me", headers=headers)
    assert subsequent_resp.status_code == 401
    assert "revoked" in str(subsequent_resp.json()).lower()


def test_refresh_revokes_old_refresh_token(unique_slug):
    """Verify that refreshing tokens invalidates the old refresh token."""
    email = f"refresh-{unique_slug}@example.com"
    pwd = "RefreshPass@123!"

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Refresh Store {unique_slug}",
            "domain": f"refresh-{unique_slug}",
            "owner_email": email,
            "owner_name": "Refresh User",
            "password": pwd,
        },
    )
    assert reg.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    tokens = login.json()
    old_refresh = tokens["refresh_token"]

    # First refresh succeeds
    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    # Second refresh with the old refresh token fails (it was blacklisted)
    second_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert second_refresh.status_code == 401


def test_change_password_invalidates_old_session(unique_slug):
    """Verify changing password revokes the old access token and accepts the new password."""
    email = f"chgpass-{unique_slug}@example.com"
    old_pwd = "OldPassword@123!"
    new_pwd = "NewPassword@123!"

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"PassStore {unique_slug}",
            "domain": f"pass-{unique_slug}",
            "owner_email": email,
            "owner_name": "Password User",
            "password": old_pwd,
        },
    )
    assert reg.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": email, "password": old_pwd})
    assert login.status_code == 200
    old_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {old_token}"}

    # Change password
    chg_resp = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": old_pwd, "new_password": new_pwd, "confirm_password": new_pwd},
        headers=headers,
    )
    assert chg_resp.status_code == 200

    # Old token must be revoked
    old_token_resp = client.get("/api/v1/users/me", headers=headers)
    assert old_token_resp.status_code == 401

    # Login with new password works
    new_login = client.post("/api/v1/auth/login", json={"email": email, "password": new_pwd})
    assert new_login.status_code == 200
    new_token = new_login.json()["access_token"]
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200


def test_active_user_suspended_tenant_recovery_rejected(unique_slug):
    """Verify that password recovery rejects active users belonging to a suspended tenant."""
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant

    email = f"susp-{unique_slug}@example.com"
    pwd = "Suspended@123!"

    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Susp Store {unique_slug}",
            "domain": f"susp-{unique_slug}",
            "owner_email": email,
            "owner_name": "Susp User",
            "password": pwd,
        },
    )
    assert reg.status_code == 200

    # Suspend tenant directly in database
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.domain == f"susp-{unique_slug}").first()
        assert tenant is not None
        tenant.is_active = False
        db.commit()
    finally:
        db.close()

    # Attempt forgot-password
    fp_resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert fp_resp.status_code == 401
    assert "tenant account is disabled" in str(fp_resp.json()).lower()

    # Attempt verify-otp
    vo_resp = client.post("/api/v1/auth/verify-otp", json={"email": email, "otp": "123456"})
    assert vo_resp.status_code == 401
    assert "tenant account is disabled" in str(vo_resp.json()).lower()

    # Attempt reset-password
    rp_resp = client.post("/api/v1/auth/reset-password", json={"token": "anytoken", "new_password": "NewPassword@123!"})
    assert rp_resp.status_code == 401


def test_store_and_user_active_security_enforcement(unique_slug):
    """Verify get_current_user enforces Store.is_active, Tenant.is_active, User.is_active, and User.is_deleted."""
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.store import Store
    from app.models.user import User
    from app.core.security import get_password_hash

    email = f"staff-sec-{unique_slug}@example.com"
    pwd = "StaffPass@123!"

    # 1. Register tenant
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Sec Store {unique_slug}",
            "domain": f"sec-{unique_slug}",
            "owner_email": f"owner-sec-{unique_slug}@example.com",
            "owner_name": "Sec Owner",
            "password": pwd,
            "plan_code": "enterprise",
        },
    )
    assert reg.status_code == 200

    # 2. Setup store and staff user directly in database
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.domain == f"sec-{unique_slug}").first()
        assert tenant is not None

        # Create active store
        store = Store(
            tenant_id=tenant.id,
            name=f"Branch {unique_slug}",
            is_active=True,
        )
        db.add(store)
        db.flush()

        # Create staff user assigned to this store
        user = User(
            tenant_id=tenant.id,
            store_id=store.id,
            role_id=1,
            email=email,
            password_hash=get_password_hash(pwd),
            full_name="Branch Cashier",
            is_active=True,
            is_deleted=False,
        )
        db.add(user)
        db.commit()
        store_id = store.id
        user_id = user.id
    finally:
        db.close()

    # Login as staff user -> obtain JWT
    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. User active + Tenant active + Store active -> SUCCESS (200)
    r1 = client.get("/api/v1/users/me", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["email"] == email

    # 2. Deactivate store -> REJECTED (401)
    db = SessionLocal()
    try:
        st = db.query(Store).filter(Store.id == store_id).first()
        st.is_active = False
        db.commit()
    finally:
        db.close()

    r2 = client.get("/api/v1/users/me", headers=headers)
    assert r2.status_code == 401
    assert "store account is disabled" in str(r2.json()).lower()

    # 3. Reactivate store -> SUCCESS (200)
    db = SessionLocal()
    try:
        st = db.query(Store).filter(Store.id == store_id).first()
        st.is_active = True
        db.commit()
    finally:
        db.close()

    r3 = client.get("/api/v1/users/me", headers=headers)
    assert r3.status_code == 200

    # 4. Suspend tenant (with active store) -> REJECTED (401)
    db = SessionLocal()
    try:
        tn = db.query(Tenant).filter(Tenant.domain == f"sec-{unique_slug}").first()
        tn.is_active = False
        db.commit()
    finally:
        db.close()

    r4 = client.get("/api/v1/users/me", headers=headers)
    assert r4.status_code == 401
    assert "tenant account is disabled" in str(r4.json()).lower()

    # 5. Reactivate tenant, deactivate user -> REJECTED (401)
    db = SessionLocal()
    try:
        tn = db.query(Tenant).filter(Tenant.domain == f"sec-{unique_slug}").first()
        tn.is_active = True
        usr = db.query(User).filter(User.id == user_id).first()
        usr.is_active = False
        db.commit()
    finally:
        db.close()

    r5 = client.get("/api/v1/users/me", headers=headers)
    assert r5.status_code == 401
    assert "user not found" in str(r5.json()).lower()

    # 6. Reactivate user, soft-delete user -> REJECTED (401)
    db = SessionLocal()
    try:
        usr = db.query(User).filter(User.id == user_id).first()
        usr.is_active = True
        usr.is_deleted = True
        db.commit()
    finally:
        db.close()

    r6 = client.get("/api/v1/users/me", headers=headers)
    assert r6.status_code == 401
    assert "user not found" in str(r6.json()).lower()


