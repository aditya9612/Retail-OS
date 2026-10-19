import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_roles_advanced_complete_flow():
    unique_slug = uuid.uuid4().hex[:8]
    owner_email = f"owner-adv-{unique_slug}@retailstore.com"

    # 1. Register tenant
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"AdvMart {unique_slug}",
            "domain": f"adv-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": "9812399991",
        },
    )
    assert reg_res.status_code == 200

    # 2. Login as Owner
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200
    owner_token = login_res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 3. Create Store 1
    store1_res = client.post(
        "/api/v1/stores/",
        headers=owner_headers,
        json={"name": "Downtown Branch", "code": "DT01"},
    )
    assert store1_res.status_code == 201
    store1_id = store1_res.json()["id"]

    # 4. Test Search and is_system filtering on GET /api/v1/roles
    all_roles_res = client.get("/api/v1/roles", headers=owner_headers)
    assert all_roles_res.status_code == 200
    all_roles = all_roles_res.json()
    assert len(all_roles) >= 6

    # Filter search by name
    search_cashier = client.get("/api/v1/roles?search=cashier", headers=owner_headers)
    assert search_cashier.status_code == 200
    cashier_results = search_cashier.json()
    assert len(cashier_results) >= 1
    assert any(r["name"] == "cashier" for r in cashier_results)

    # Filter is_system=true
    system_roles = client.get("/api/v1/roles?is_system=true", headers=owner_headers)
    assert system_roles.status_code == 200
    for r in system_roles.json():
        assert r["is_system"] is True

    # 5. Test RBAC Permissions Matrix Endpoint: GET /api/v1/roles/matrix
    matrix_res = client.get("/api/v1/roles/matrix", headers=owner_headers)
    assert matrix_res.status_code == 200
    matrix_data = matrix_res.json()
    assert "roles" in matrix_data
    assert "modules" in matrix_data
    assert len(matrix_data["roles"]) >= 6
    assert len(matrix_data["modules"]) >= 5

    billing_module = next((m for m in matrix_data["modules"] if m["module"] == "billing"), None)
    assert billing_module is not None
    assert len(billing_module["permissions"]) >= 1
    # Check that owner has access
    billing_read_perm = next((p for p in billing_module["permissions"] if p["code"] == "billing:read"), None)
    assert billing_read_perm is not None
    assert billing_read_perm["role_access"].get("owner") is True

    # 6. Create custom role: "temp_cashier"
    create_role_res = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={
            "name": "temp_cashier",
            "description": "Temporary cashier role for festive season",
            "permissions": ["products:read", "billing:read", "billing:write", "payments:write"],
        },
    )
    assert create_role_res.status_code == 201
    temp_role = create_role_res.json()
    temp_role_id = temp_role["id"]
    assert temp_role["name"] == "temp_cashier"

    # Ensure quota for users
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.saas_billing import SaaSSubscription
    from app.models.saas_plan_entitlement import SaaSPlanEntitlement, EntitlementDimension

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.domain == f"adv-{unique_slug}").first()
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

    # 7. Create 2 users under "temp_cashier"
    u1_res = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": f"u1-{unique_slug}@store.com",
            "full_name": "Temp User One",
            "password": "Password@123!",
            "role": "temp_cashier",
            "phone": "9812399992",
            "store_id": store1_id,
        },
    )
    assert u1_res.status_code == 201
    u1_id = u1_res.json()["id"]

    u2_res = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": f"u2-{unique_slug}@store.com",
            "full_name": "Temp User Two",
            "password": "Password@123!",
            "role": "temp_cashier",
            "phone": "9812399993",
            "store_id": store1_id,
        },
    )
    assert u2_res.status_code == 201
    u2_id = u2_res.json()["id"]

    # 8. Test GET /api/v1/roles/{role_id}/users
    role_users_res = client.get(f"/api/v1/roles/{temp_role_id}/users", headers=owner_headers)
    assert role_users_res.status_code == 200
    role_users_data = role_users_res.json()
    assert role_users_data["role_id"] == temp_role_id
    assert role_users_data["role_name"] == "temp_cashier"
    assert role_users_data["total_users"] == 2
    user_ids = [u["id"] for u in role_users_data["users"]]
    assert u1_id in user_ids
    assert u2_id in user_ids

    # Store filter test
    store_filter_res = client.get(f"/api/v1/roles/{temp_role_id}/users?store_id={store1_id}", headers=owner_headers)
    assert store_filter_res.status_code == 200
    assert store_filter_res.json()["total_users"] == 2

    # 9. Attempting to delete temp_cashier fails because 2 users are assigned -> 409
    del_blocked = client.delete(f"/api/v1/roles/{temp_role_id}", headers=owner_headers)
    assert del_blocked.status_code == 409

    # 10. Test Bulk Reassign Users: POST /api/v1/roles/{role_id}/reassign-users
    # Find role 'staff'
    staff_role = next(r for r in all_roles if r["name"] == "staff")
    staff_role_id = staff_role["id"]

    # Self-reassignment fails with 409
    self_reassign = client.post(
        f"/api/v1/roles/{temp_role_id}/reassign-users",
        headers=owner_headers,
        json={"target_role_id": temp_role_id},
    )
    assert self_reassign.status_code == 409

    # Successful bulk reassign from temp_cashier to staff
    reassign_res = client.post(
        f"/api/v1/roles/{temp_role_id}/reassign-users",
        headers=owner_headers,
        json={"target_role_id": staff_role_id},
    )
    assert reassign_res.status_code == 200
    reassign_data = reassign_res.json()
    assert reassign_data["source_role_id"] == temp_role_id
    assert reassign_data["target_role_id"] == staff_role_id
    assert reassign_data["reassigned_count"] == 2

    # Now verify temp_cashier has 0 users
    after_reassign_users = client.get(f"/api/v1/roles/{temp_role_id}/users", headers=owner_headers)
    assert after_reassign_users.json()["total_users"] == 0

    # 11. Now delete the empty role -> Returns RoleDeleteResponse
    del_success = client.delete(f"/api/v1/roles/{temp_role_id}", headers=owner_headers)
    assert del_success.status_code == 200
    del_data = del_success.json()
    assert del_data["deleted_role_id"] == temp_role_id
    assert "deleted successfully" in del_data["message"]

    # 12. Test Reset Default Role to Official Permissions: POST /api/v1/roles/{role_id}/reset-default
    cashier_role = next(r for r in all_roles if r["name"] == "cashier")
    cashier_id = cashier_role["id"]

    # First, modify cashier permissions to something minimal
    patch_cashier = client.patch(
        f"/api/v1/roles/{cashier_id}",
        headers=owner_headers,
        json={"permissions": ["products:read"]},
    )
    assert patch_cashier.status_code == 200
    assert patch_cashier.json()["permissions"] == ["products:read"]

    # Reset cashier to default
    reset_res = client.post(
        f"/api/v1/roles/{cashier_id}/reset-default",
        headers=owner_headers,
    )
    assert reset_res.status_code == 200
    reset_data = reset_res.json()
    assert "billing:read" in reset_data["permissions"]
    assert "orders:read" in reset_data["permissions"]
    assert len(reset_data["permissions"]) >= 5

    # Reset on non-default/custom role should fail with 409 Conflict
    new_custom_role = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={"name": "custom_audit", "permissions": ["reports:read"]},
    ).json()
    reset_custom_fail = client.post(
        f"/api/v1/roles/{new_custom_role['id']}/reset-default",
        headers=owner_headers,
    )
    assert reset_custom_fail.status_code == 409
