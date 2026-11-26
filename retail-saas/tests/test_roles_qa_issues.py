import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_rohit_pawar_qa_reported_issues():
    unique_slug = uuid.uuid4().hex[:8]
    owner_email = f"qa-owner-{unique_slug}@retailmart.com"

    # Register tenant
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"QAMart {unique_slug}",
            "domain": f"qa-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "QA Store Owner",
            "password": "Password@123!",
            "owner_phone": "9819998881",
        },
    )
    assert reg_res.status_code == 200

    # Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Issue 4 Verification: Cashier role is immediately visible in list_roles
    list_res = client.get("/api/v1/roles", headers=headers)
    assert list_res.status_code == 200
    roles = list_res.json()["items"]
    role_names = [r["name"] for r in roles]
    assert "cashier" in role_names, "Cashier role MUST be available in list_roles"
    cashier_role = next(r for r in roles if r["name"] == "cashier")
    cashier_id = cashier_role["id"]

    # Issue 1 Verification: GET /api/v1/roles accepts number / ID in search
    search_by_id = client.get(f"/api/v1/roles?search={cashier_id}", headers=headers)
    assert search_by_id.status_code == 200
    id_results = search_by_id.json()["items"]
    assert any(r["id"] == cashier_id for r in id_results), "Search with numeric ID must return matching role"

    # Direct role_id filter parameter
    direct_id_filter = client.get(f"/api/v1/roles?role_id={cashier_id}", headers=headers)
    assert direct_id_filter.status_code == 200
    assert len(direct_id_filter.json()["items"]) == 1
    assert direct_id_filter.json()["items"][0]["id"] == cashier_id

    # Issue 2 Verification: Exact match filter on name returns exactly 1 response
    exact_name_res = client.get("/api/v1/roles?name=manager", headers=headers)
    assert exact_name_res.status_code == 200
    exact_list = exact_name_res.json()["items"]
    assert len(exact_list) == 1
    assert exact_list[0]["name"] == "manager"

    # Issue 3 Verification: Roles endpoint accepts BOTH numeric ID and role name string
    # By ID:
    get_by_id = client.get(f"/api/v1/roles/{cashier_id}", headers=headers)
    assert get_by_id.status_code == 200
    assert get_by_id.json()["id"] == cashier_id
    assert get_by_id.json()["name"] == "cashier"

    # By Name:
    get_by_name = client.get("/api/v1/roles/cashier", headers=headers)
    assert get_by_name.status_code == 200
    assert get_by_name.json()["id"] == cashier_id
    assert get_by_name.json()["name"] == "cashier"

    # Issue 5 Verification: PATCH /api/v1/roles/{role_id} returns 200 OK without 500 error
    patch_by_id = client.patch(
        f"/api/v1/roles/{cashier_id}",
        headers=headers,
        json={
            "description": "Updated cashier responsibilities",
            "permissions": ["billing:create", "billing:read", "products:read"],
        },
    )
    assert patch_by_id.status_code == 200
    assert patch_by_id.json()["permissions"] == ["billing:create", "billing:read", "products:read"]

    # Also PATCH by role name
    patch_by_name = client.patch(
        "/api/v1/roles/cashier",
        headers=headers,
        json={"permissions": ["billing:create", "billing:read", "products:read", "customers:read"]},
    )
    assert patch_by_name.status_code == 200
    assert "customers:read" in patch_by_name.json()["permissions"]

    # Issue 6 Verification: GET /api/v1/roles/{role_id}/users accepts 'null', 'none', 'unassigned' as store_id
    # Create a user with store_id = None (unassigned)
    u_res = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"cashier-unassigned-{unique_slug}@store.com",
            "full_name": "Unassigned Cashier",
            "password": "Password@123!",
            "role": "cashier",
            "phone": "9819998882",
            # store_id is None by default
        },
    )
    assert u_res.status_code == 201
    assert u_res.json()["store_id"] is None

    # Filter with store_id="null" - must NOT fail with 422!
    users_null_store = client.get(f"/api/v1/roles/{cashier_id}/users?store_id=null", headers=headers)
    assert users_null_store.status_code == 200
    null_users_data = users_null_store.json()
    assert null_users_data["total_users"] >= 1
    for u in null_users_data["users"]:
        assert u["store_id"] is None

    # Filter with store_id="unassigned"
    users_unassigned = client.get(f"/api/v1/roles/{cashier_id}/users?store_id=unassigned", headers=headers)
    assert users_unassigned.status_code == 200
    assert users_unassigned.json()["total_users"] >= 1

    # Also access by role name in users endpoint: GET /api/v1/roles/cashier/users
    users_by_name = client.get("/api/v1/roles/cashier/users?store_id=null", headers=headers)
    assert users_by_name.status_code == 200
    assert users_by_name.json()["role_name"] == "cashier"
