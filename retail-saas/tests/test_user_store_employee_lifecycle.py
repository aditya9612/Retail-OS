import random
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.role import Role

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


def _register_and_login_tenant(slug_prefix: str):
    suffix = uuid.uuid4().hex[:6]
    owner_email = f"owner_{slug_prefix}_{suffix}@testmart.com"
    owner_pass = "Password@123!"
    owner_phone = _gen_phone()

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Mart {slug_prefix} {suffix}",
            "domain": f"{slug_prefix}-{suffix}",
            "owner_email": owner_email,
            "owner_name": f"Owner {slug_prefix}",
            "password": owner_pass,
            "owner_phone": owner_phone,
            "plan_code": "enterprise",
        },
    )
    assert reg_res.status_code == 200, f"Register failed: {reg_res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": owner_pass},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = reg_res.json()["tenant_id"]

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "owner_email": owner_email,
        "owner_pass": owner_pass,
        "suffix": suffix,
    }


def test_employee_complete_lifecycle_flow(unique_slug):
    """
    Complete lifecycle verification:
    CREATE -> ASSIGN STORE -> ACTIVE -> UPDATE -> TRANSFER STORE -> REMOVE STORE -> DEACTIVATE -> REACTIVATE -> SOFT DELETE
    """
    ctx = _register_and_login_tenant(f"lc-{unique_slug}")
    headers = ctx["headers"]
    suffix = ctx["suffix"]

    # 1. Create Store 1 & Store 2
    s1_res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={"name": f"Branch Alpha {suffix}", "code": f"B1{suffix[:4].upper()}"},
    )
    assert s1_res.status_code == 201
    store1_id = s1_res.json()["id"]

    s2_res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={"name": f"Branch Beta {suffix}", "code": f"B2{suffix[:4].upper()}"},
    )
    assert s2_res.status_code == 201
    store2_id = s2_res.json()["id"]

    # 2. CREATE employee initially unassigned to any store
    emp_email = f"emp_{suffix}@testmart.com"
    emp_pass = "EmployeePass@123!"
    emp_phone = _gen_phone()
    create_res = client.post(
        "/api/v1/users",
        headers=headers,
        data={
            "email": emp_email,
            "full_name": "Ramesh Kumar",
            "password": emp_pass,
            "role": "staff",
            "phone": emp_phone,
        },
    )
    assert create_res.status_code == 201, f"Create user failed: {create_res.text}"
    emp = create_res.json()
    emp_id = emp["id"]
    assert emp["email"] == emp_email
    assert emp["is_active"] is True
    assert emp["store_id"] is None

    # 3. ASSIGN STORE to Store 1 (Verifies POST and PATCH alias)
    assign_patch = client.patch(
        f"/api/v1/users/{emp_id}/assign-store",
        headers=headers,
        json={"store_id": store1_id},
    )
    assert assign_patch.status_code == 200
    assert assign_patch.json()["store_id"] == store1_id

    # 4. ACTIVE: Employee can log in with their credentials
    login_emp = client.post(
        "/api/v1/auth/login",
        json={"email": emp_email, "password": emp_pass},
    )
    assert login_emp.status_code == 200
    assert "access_token" in login_emp.json()

    # Verify user record shows active and assigned to store1
    emp_details = client.get(f"/api/v1/users/{emp_id}", headers=headers).json()
    assert emp_details["id"] == emp_id
    assert emp_details["is_active"] is True
    assert emp_details["store_id"] == store1_id

    # 5. UPDATE: Full name and phone update via PUT and PATCH alias
    new_phone = _gen_phone()
    put_res = client.put(
        f"/api/v1/users/{emp_id}",
        headers=headers,
        json={"full_name": "Ramesh Kumar Updated"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["full_name"] == "Ramesh Kumar Updated"

    patch_res = client.patch(
        f"/api/v1/users/{emp_id}",
        headers=headers,
        json={"phone": new_phone},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["phone"] == new_phone

    # 6. TRANSFER STORE to Store 2 (via assign-store)
    transfer_res = client.post(
        f"/api/v1/users/{emp_id}/assign-store",
        headers=headers,
        json={"store_id": store2_id},
    )
    assert transfer_res.status_code == 200
    assert transfer_res.json()["store_id"] == store2_id

    # 7. REMOVE STORE: unassign user back to null store_id (Verifies POST and PATCH alias)
    remove_patch = client.patch(
        f"/api/v1/users/{emp_id}/remove-store",
        headers=headers,
        json={"store_id": store2_id},
    )
    assert remove_patch.status_code == 200
    assert remove_patch.json()["store_id"] is None
    assert remove_patch.json()["previous_store_id"] == store2_id

    # Re-assign and test POST remove-store
    client.post(
        f"/api/v1/users/{emp_id}/assign-store",
        headers=headers,
        json={"store_id": store1_id},
    )
    remove_post = client.post(
        f"/api/v1/users/{emp_id}/remove-store",
        headers=headers,
    )
    assert remove_post.status_code == 200
    assert remove_post.json()["store_id"] is None

    # 8. DEACTIVATE employee
    deact_res = client.patch(
        f"/api/v1/users/{emp_id}/deactivate",
        headers=headers,
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # Deactivated user cannot login
    assert client.post(
        "/api/v1/auth/login",
        json={"email": emp_email, "password": emp_pass},
    ).status_code == 401

    # 9. REACTIVATE employee
    react_res = client.patch(
        f"/api/v1/users/{emp_id}/activate",
        headers=headers,
    )
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True

    # 10. SOFT DELETE employee
    del_res = client.delete(
        f"/api/v1/users/{emp_id}",
        headers=headers,
    )
    assert del_res.status_code == 204

    # Deleted user cannot be retrieved by ID (404)
    assert client.get(f"/api/v1/users/{emp_id}", headers=headers).status_code == 404

    # Deleted user cannot be reactivated
    react_del_res = client.patch(f"/api/v1/users/{emp_id}/activate", headers=headers)
    assert react_del_res.status_code in (404, 409)

    # Deleted user cannot authenticate
    assert client.post(
        "/api/v1/auth/login",
        json={"email": emp_email, "password": emp_pass},
    ).status_code == 401


def test_role_escalation_security_enforcement(unique_slug):
    """
    Security verification:
    Store-scoped users cannot promote users to ADMIN or OWNER or privileged roles.
    Tenant Owner / Admin can perform legitimate role updates.
    """
    ctx = _register_and_login_tenant(f"re-{unique_slug}")
    owner_headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    suffix = ctx["suffix"]

    # 1. Create Store 1
    s1_res = client.post(
        "/api/v1/stores/",
        headers=owner_headers,
        json={"name": f"Store Alpha {suffix}", "code": f"S1{suffix[:4].upper()}"},
    )
    assert s1_res.status_code == 201
    store1_id = s1_res.json()["id"]

    # 2. Setup roles
    db = SessionLocal()
    try:
        # Give Manager users:read, users:write for Store 1 testing
        mgr_role = db.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "manager").first()
        mgr_role.permissions = ["users:read", "users:write", "stores:read"]

        # Find admin & owner role IDs
        admin_role = db.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "admin").first()
        owner_role = db.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "owner").first()
        cashier_role = db.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "cashier").first()
        staff_role = db.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "staff").first()

        # Create custom privileged role with stores:write
        custom_priv_role = Role(
            tenant_id=tenant_id,
            name="custom_ops_admin",
            permissions=["stores:write", "billing:price_override"],
        )
        db.add(custom_priv_role)
        db.commit()
        db.refresh(custom_priv_role)
        db.refresh(admin_role)
        db.refresh(owner_role)
        db.refresh(cashier_role)
        db.refresh(staff_role)

        admin_role_id = admin_role.id
        owner_role_id = owner_role.id
        cashier_role_id = cashier_role.id
        staff_role_id = staff_role.id
        custom_priv_role_id = custom_priv_role.id
    finally:
        db.close()

    # 3. Create Manager for Store 1
    mgr_email = f"mgr_{suffix}@testmart.com"
    mgr_pass = "ManagerPass@123!"
    r_mgr = client.post(
        "/api/v1/users",
        headers=owner_headers,
        data={
            "email": mgr_email,
            "full_name": "Store Manager Alpha",
            "password": mgr_pass,
            "role": "manager",
            "store_id": store1_id,
            "phone": _gen_phone(),
        },
    )
    assert r_mgr.status_code == 201

    # Login as Store 1 Manager
    login_mgr = client.post(
        "/api/v1/auth/login",
        json={"email": mgr_email, "password": mgr_pass},
    )
    mgr_token = login_mgr.json()["access_token"]
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

    # 4. Create Staff in Store 1
    target_staff_email = f"target_staff_{suffix}@testmart.com"
    r_target = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": target_staff_email,
            "full_name": "Target Staff Person",
            "password": "Password@123!",
            "role": "staff",
            "phone": _gen_phone(),
            "store_id": store1_id,
        },
    )
    assert r_target.status_code == 201
    target_staff_id = r_target.json()["id"]

    # ========================================================
    # SECURITY TEST 1: Manager attempts to promote staff to ADMIN -> MUST BE 403
    # ========================================================
    esc_admin_res = client.patch(
        f"/api/v1/users/{target_staff_id}",
        headers=mgr_headers,
        json={"role_id": admin_role_id},
    )
    assert esc_admin_res.status_code == 403, f"Expected 403, got {esc_admin_res.status_code}: {esc_admin_res.text}"
    assert "cannot assign tenant administrator" in str(esc_admin_res.json()).lower()

    # ========================================================
    # SECURITY TEST 2: Manager attempts to promote staff to OWNER -> MUST BE 403
    # ========================================================
    esc_owner_res = client.patch(
        f"/api/v1/users/{target_staff_id}",
        headers=mgr_headers,
        json={"role_id": owner_role_id},
    )
    assert esc_owner_res.status_code == 403, f"Expected 403, got {esc_owner_res.status_code}: {esc_owner_res.text}"
    assert "cannot assign tenant administrator" in str(esc_owner_res.json()).lower()

    # ========================================================
    # SECURITY TEST 3: Manager attempts to assign custom privileged role -> MUST BE 403
    # ========================================================
    esc_priv_res = client.patch(
        f"/api/v1/users/{target_staff_id}",
        headers=mgr_headers,
        json={"role_id": custom_priv_role_id},
    )
    assert esc_priv_res.status_code == 403, f"Expected 403, got {esc_priv_res.status_code}: {esc_priv_res.text}"
    assert "cannot assign tenant administrator" in str(esc_priv_res.json()).lower()

    # ========================================================
    # SECURITY TEST 4: Manager CAN perform legitimate store-level role update
    # staff -> cashier
    # ========================================================
    legit_res = client.patch(
        f"/api/v1/users/{target_staff_id}",
        headers=mgr_headers,
        json={"role_id": cashier_role_id},
    )
    assert legit_res.status_code == 200, f"Expected 200, got {legit_res.status_code}: {legit_res.text}"
    assert legit_res.json()["role_id"] == cashier_role_id

    # cashier -> staff
    legit_res2 = client.patch(
        f"/api/v1/users/{target_staff_id}",
        headers=mgr_headers,
        json={"role_id": staff_role_id},
    )
    assert legit_res2.status_code == 200
    assert legit_res2.json()["role_id"] == staff_role_id

    # ========================================================
    # SECURITY TEST 5: Tenant Owner (store_id=None) CAN assign admin role
    # ========================================================
    owner_assign_admin = client.patch(
        f"/api/v1/users/{target_staff_id}",
        headers=owner_headers,
        json={"role_id": admin_role_id},
    )
    assert owner_assign_admin.status_code == 200
    assert owner_assign_admin.json()["role_id"] == admin_role_id


def test_cross_tenant_and_store_isolation_negatives(unique_slug):
    """
    Negative tests verifying strict multi-tenant and cross-store isolation:
    - Tenant A cannot access/update/delete Tenant B user
    - Tenant A cannot assign Tenant B store
    - Store Manager cannot access/update/delete users of another store
    - Store Manager cannot assign stores
    - Self-deactivation and self-deletion are rejected
    """
    # 1. Register Tenant A & Tenant B
    ctx_a = _register_and_login_tenant(f"ta-{unique_slug}")
    headers_a = ctx_a["headers"]
    suffix_a = ctx_a["suffix"]

    ctx_b = _register_and_login_tenant(f"tb-{unique_slug}")
    headers_b = ctx_b["headers"]
    suffix_b = ctx_b["suffix"]

    # Stores
    s_a = client.post("/api/v1/stores/", headers=headers_a, json={"name": f"Store Alpha {suffix_a}", "code": f"A{suffix_a[:4].upper()}"})
    assert s_a.status_code == 201
    store_a1_id = s_a.json()["id"]

    s_a2 = client.post("/api/v1/stores/", headers=headers_a, json={"name": f"Store Beta {suffix_a}", "code": f"A2{suffix_a[:3].upper()}"})
    assert s_a2.status_code == 201
    store_a2_id = s_a2.json()["id"]

    s_b = client.post("/api/v1/stores/", headers=headers_b, json={"name": f"Store Gamma {suffix_b}", "code": f"B{suffix_b[:4].upper()}"})
    assert s_b.status_code == 201
    store_b_id = s_b.json()["id"]

    # Users
    u_a1 = client.post(
        "/api/v1/users",
        headers=headers_a,
        json={"email": f"u_a1_{suffix_a}@mart.com", "full_name": "User Alpha", "password": "Password@123!", "role": "staff", "phone": _gen_phone(), "store_id": store_a1_id},
    ).json()
    user_a1_id = u_a1["id"]

    u_a2 = client.post(
        "/api/v1/users",
        headers=headers_a,
        json={"email": f"u_a2_{suffix_a}@mart.com", "full_name": "User Beta", "password": "Password@123!", "role": "staff", "phone": _gen_phone(), "store_id": store_a2_id},
    ).json()
    user_a2_id = u_a2["id"]

    u_b = client.post(
        "/api/v1/users",
        headers=headers_b,
        json={"email": f"u_b_{suffix_b}@mart.com", "full_name": "User Gamma", "password": "Password@123!", "role": "staff", "phone": _gen_phone(), "store_id": store_b_id},
    ).json()
    user_b_id = u_b["id"]

    # --- CROSS-TENANT NEGATIVES ---
    # Tenant A attempts to GET Tenant B user -> MUST be 404
    assert client.get(f"/api/v1/users/{user_b_id}", headers=headers_a).status_code == 404

    # Tenant A attempts to UPDATE Tenant B user -> MUST be 404
    assert client.patch(f"/api/v1/users/{user_b_id}", headers=headers_a, json={"full_name": "Hacked Name"}).status_code == 404

    # Tenant A attempts to DELETE Tenant B user -> MUST be 404
    assert client.delete(f"/api/v1/users/{user_b_id}", headers=headers_a).status_code == 404

    # Tenant A attempts to DEACTIVATE Tenant B user -> MUST be 404
    assert client.patch(f"/api/v1/users/{user_b_id}/deactivate", headers=headers_a).status_code == 404

    # Tenant A attempts to assign User A1 to Store B -> MUST be 404
    assert client.post(f"/api/v1/users/{user_a1_id}/assign-store", headers=headers_a, json={"store_id": store_b_id}).status_code == 404

    # --- STORE ISOLATION NEGATIVES ---
    # Setup Manager for Store A1 with users:read and users:write
    db = SessionLocal()
    try:
        mgr_role = db.query(Role).filter(Role.tenant_id == ctx_a["tenant_id"], Role.name == "manager").first()
        mgr_role.permissions = ["users:read", "users:write", "stores:read"]
        db.commit()
    finally:
        db.close()

    mgr_a1_email = f"mgr_a1_{suffix_a}@mart.com"
    client.post(
        "/api/v1/users",
        headers=headers_a,
        data={"email": mgr_a1_email, "full_name": "Manager Alpha", "password": "Password@123!", "role": "manager", "store_id": store_a1_id, "phone": _gen_phone()},
    )
    login_mgr = client.post("/api/v1/auth/login", json={"email": mgr_a1_email, "password": "Password@123!"})
    mgr_headers = {"Authorization": f"Bearer {login_mgr.json()['access_token']}"}

    # Store 1 Manager CANNOT access Store 2 user -> MUST be 403
    assert client.get(f"/api/v1/users/{user_a2_id}", headers=mgr_headers).status_code == 403

    # Store 1 Manager CANNOT update Store 2 user -> MUST be 403
    assert client.patch(f"/api/v1/users/{user_a2_id}", headers=mgr_headers, json={"full_name": "Hacked Manager"}).status_code == 403

    # Store 1 Manager CANNOT delete Store 2 user -> MUST be 403
    assert client.delete(f"/api/v1/users/{user_a2_id}", headers=mgr_headers).status_code == 403

    # Store 1 Manager CANNOT list Store 2 users via /users?store_id={store_id} -> MUST be 403
    assert client.get(f"/api/v1/users?store_id={store_a2_id}", headers=mgr_headers).status_code == 403

    # Removed /stores/{store_id}/users endpoint MUST return 404
    assert client.get(f"/api/v1/stores/{store_a2_id}/users", headers=mgr_headers).status_code == 404

    # Store 1 Manager CANNOT assign users to stores -> MUST be 403
    assert client.post(f"/api/v1/users/{user_a1_id}/assign-store", headers=mgr_headers, json={"store_id": store_a1_id}).status_code == 403

    # Store 1 Manager CANNOT create new store -> MUST be 403
    assert client.post("/api/v1/stores/", headers=mgr_headers, json={"name": "Forbidden Branch", "code": "FB01"}).status_code == 403

    # --- SELF PROTECTION NEGATIVES ---
    # Store Owner cannot deactivate themselves -> MUST be 409
    me = client.get("/api/v1/users/me", headers=headers_a).json()
    assert client.patch(f"/api/v1/users/{me['id']}/deactivate", headers=headers_a).status_code == 409

    # Store Owner cannot delete themselves -> MUST be 409
    assert client.delete(f"/api/v1/users/{me['id']}", headers=headers_a).status_code == 409
