import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_role_management_full_flow(unique_slug):
    # 1. Register a new tenant (Store Owner)
    owner_email = f"owner-{unique_slug}@retailstore.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"SuperMart {unique_slug}",
            "domain": f"sm-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "owner_phone": "9812345670",
        },
    )
    assert reg_res.status_code == 200

    # 2. Login as Store Owner
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200
    owner_token = login_res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 3. Create Store 1 and Store 2
    store1_res = client.post(
        "/api/v1/stores/",
        headers=owner_headers,
        json={"name": "Downtown Branch", "code": "DT01"},
    )
    assert store1_res.status_code == 201
    store1_id = store1_res.json()["id"]

    store2_res = client.post(
        "/api/v1/stores/",
        headers=owner_headers,
        json={"name": "Uptown Branch", "code": "UP02"},
    )
    assert store2_res.status_code == 201
    store2_id = store2_res.json()["id"]

    # 4. Check available system permissions endpoint
    perms_res = client.get("/api/v1/roles/permissions", headers=owner_headers)
    assert perms_res.status_code == 200
    perm_groups = perms_res.json()
    assert len(perm_groups) >= 5
    modules = [g["module"] for g in perm_groups]
    assert "billing" in modules
    assert "inventory" in modules
    assert "orders" in modules

    # 5. List default roles (should contain admin, owner, manager, accountant, cashier, staff)
    roles_res = client.get("/api/v1/roles", headers=owner_headers)
    assert roles_res.status_code == 200
    roles = roles_res.json()
    role_names = [r["name"] for r in roles]
    assert "owner" in role_names
    assert "admin" in role_names
    assert "manager" in role_names
    assert "accountant" in role_names
    assert "cashier" in role_names
    assert "staff" in role_names

    # 6. Verify removed /api/v1/users/roles returns 404
    removed_roles_res = client.get("/api/v1/users/roles", headers=owner_headers)
    assert removed_roles_res.status_code in [404, 422]

    # 7. Owner creates a custom role (e.g. "inventory_supervisor")
    create_role_res = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={
            "name": "inventory_supervisor",
            "permissions": [
                "products:read",
                "products:write",
                "inventory:read",
                "inventory:write",
            ],
        },
    )
    assert create_role_res.status_code == 201
    custom_role = create_role_res.json()
    custom_role_id = custom_role["id"]
    assert custom_role["name"] == "inventory_supervisor"
    assert "inventory:read" in custom_role["permissions"]
    assert custom_role["user_count"] == 0

    # 8. Duplicate role name returns 409 Conflict
    dup_res = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={"name": "inventory_supervisor", "permissions": []},
    )
    assert dup_res.status_code == 409

    # 9. Get custom role details by ID
    get_role_res = client.get(f"/api/v1/roles/{custom_role_id}", headers=owner_headers)
    assert get_role_res.status_code == 200
    assert get_role_res.json()["name"] == "inventory_supervisor"

    # 10. Update role permissions
    patch_res = client.patch(
        f"/api/v1/roles/{custom_role_id}",
        headers=owner_headers,
        json={"permissions": ["products:read", "inventory:read"]},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["permissions"] == ["products:read", "inventory:read"]

    # Ensure tenant has users quota for test
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.saas_billing import SaaSSubscription
    from app.models.saas_plan_entitlement import SaaSPlanEntitlement, EntitlementDimension

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.domain == f"sm-{unique_slug}").first()
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

    # 11. Create MULTIPLE users under this SINGLE custom role across different stores!
    # User 1: assigned to Store 1
    user1_email = f"supervisor1-{unique_slug}@retailstore.com"
    user1_res = client.post(
        f"/api/v1/stores/{store1_id}/users",
        headers=owner_headers,
        json={
            "email": user1_email,
            "full_name": "Supervisor One",
            "password": "Password@123!",
            "role": "inventory_supervisor",
            "phone": "9812345671",
        },
    )
    assert user1_res.status_code == 201
    user1_data = user1_res.json()
    assert user1_data["role_id"] == custom_role_id
    assert user1_data["store_id"] == store1_id

    # User 2: assigned to Store 2
    user2_email = f"supervisor2-{unique_slug}@retailstore.com"
    user2_res = client.post(
        f"/api/v1/stores/{store2_id}/users",
        headers=owner_headers,
        json={
            "email": user2_email,
            "full_name": "Supervisor Two",
            "password": "Password@123!",
            "role_id": custom_role_id,
            "phone": "9812345672",
        },
    )
    assert user2_res.status_code == 201
    user2_data = user2_res.json()
    assert user2_data["role_id"] == custom_role_id
    assert user2_data["store_id"] == store2_id

    # 12. Verify user count for the custom role is now 2
    role_check_res = client.get(f"/api/v1/roles/{custom_role_id}", headers=owner_headers)
    assert role_check_res.status_code == 200
    assert role_check_res.json()["user_count"] == 2

    # 12b. Verify GET /api/v1/users/by-store (Store Users Allocation breakdown)
    by_store_res = client.get("/api/v1/users/by-store", headers=owner_headers)
    assert by_store_res.status_code == 200
    by_store_data = by_store_res.json()
    assert by_store_data["total_stores"] >= 2
    assert by_store_data["total_users"] >= 3

    # Verify Store 1 has User 1
    s1_entry = next(s for s in by_store_data["stores"] if s["store_id"] == store1_id)
    assert s1_entry["store_name"] == "Downtown Branch"
    assert s1_entry["total_users"] == 1
    assert s1_entry["users"][0]["email"] == user1_email
    assert s1_entry["users"][0]["role_name"] == "inventory_supervisor"

    # Verify Store 2 has User 2
    s2_entry = next(s for s in by_store_data["stores"] if s["store_id"] == store2_id)
    assert s2_entry["store_name"] == "Uptown Branch"
    assert s2_entry["total_users"] == 1
    assert s2_entry["users"][0]["email"] == user2_email
    assert s2_entry["users"][0]["role_name"] == "inventory_supervisor"

    # Verify unassigned / head office has the owner
    unassigned_entry = next((s for s in by_store_data["stores"] if s["store_id"] is None), None)
    assert unassigned_entry is not None
    assert any(u["email"] == owner_email for u in unassigned_entry["users"])

    # 12c. Test filters on GET /api/v1/users/by-store
    # Filter by store_id
    filter_store_res = client.get(f"/api/v1/users/by-store?store_id={store1_id}", headers=owner_headers)
    assert filter_store_res.status_code == 200
    filter_store_data = filter_store_res.json()
    assert filter_store_data["total_stores"] == 1
    assert filter_store_data["stores"][0]["store_id"] == store1_id
    assert filter_store_data["stores"][0]["total_users"] == 1

    # Filter by role name
    filter_role_res = client.get("/api/v1/users/by-store?role=inventory_supervisor", headers=owner_headers)
    assert filter_role_res.status_code == 200
    filter_role_data = filter_role_res.json()
    for s in filter_role_data["stores"]:
        for u in s["users"]:
            assert u["role_name"] == "inventory_supervisor"

    # Filter by search
    search_res = client.get("/api/v1/users/by-store?search=Supervisor%20One", headers=owner_headers)
    assert search_res.status_code == 200
    search_data = search_res.json()
    found_users = [u for s in search_data["stores"] for u in s["users"]]
    assert len(found_users) == 1
    assert found_users[0]["full_name"] == "Supervisor One"

    # Filter include_unassigned=false
    no_unassigned_res = client.get("/api/v1/users/by-store?include_unassigned=false", headers=owner_headers)
    assert no_unassigned_res.status_code == 200
    no_unassigned_data = no_unassigned_res.json()
    assert all(s["store_id"] is not None for s in no_unassigned_data["stores"])

    # 13. Attempt to delete custom role while users are assigned -> MUST FAIL with 409 Conflict
    del_fail_res = client.delete(f"/api/v1/roles/{custom_role_id}", headers=owner_headers)
    assert del_fail_res.status_code == 409
    err_msg = del_fail_res.json()["detail"]
    if isinstance(err_msg, dict):
        err_msg = err_msg.get("message", "")
    assert "assigned" in err_msg.lower()

    # 14. Attempt to delete core system roles (e.g. manager, owner) -> MUST FAIL with 409 Conflict
    manager_role = next(r for r in roles if r["name"] == "manager")
    del_core_res = client.delete(f"/api/v1/roles/{manager_role['id']}", headers=owner_headers)
    assert del_core_res.status_code == 409

    # 15. Store staff cannot create/delete roles (RBAC check)
    user1_login = client.post(
        "/api/v1/auth/login",
        json={"email": user1_email, "password": "Password@123!"},
    )
    assert user1_login.status_code == 200
    user1_headers = {"Authorization": f"Bearer {user1_login.json()['access_token']}"}

    staff_create_role = client.post(
        "/api/v1/roles",
        headers=user1_headers,
        json={"name": "hacker_role", "permissions": ["*"]},
    )
    assert staff_create_role.status_code in [401, 403]

    # 16. Reassign or delete users so role can be safely deleted
    client.delete(f"/api/v1/users/{user1_data['id']}", headers=owner_headers)
    client.delete(f"/api/v1/users/{user2_data['id']}", headers=owner_headers)

    # 17. Now delete the custom role -> Succeeds
    del_success_res = client.delete(f"/api/v1/roles/{custom_role_id}", headers=owner_headers)
    assert del_success_res.status_code == 200
    assert del_success_res.json()["deleted_role_id"] == custom_role_id

    # 18. Verify role no longer exists
    get_after_del = client.get(f"/api/v1/roles/{custom_role_id}", headers=owner_headers)
    assert get_after_del.status_code == 404
