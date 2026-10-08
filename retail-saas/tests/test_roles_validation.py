import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_role_name_and_permissions_strict_validation(unique_slug):
    # 1. Register and login Store Owner
    owner_email = f"owner-roles-{unique_slug}@retailstore.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"RolesMart {unique_slug}",
            "domain": f"rm-{unique_slug}",
            "owner_email": owner_email,
            "owner_name": "Roles Owner",
            "password": "Password@123!",
            "owner_phone": "9812345679",
        },
    )
    assert reg_res.status_code == 200

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200
    owner_token = login_res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Test invalid role names (e.g. "000" reported by tester) -> MUST BE 422
    invalid_names = [
        "000",
        "12345",
        "---",
        "___",
        "-cashier",
        "cashier-",
        "_manager",
        "manager_",
        "a",
        "",
        "   ",
        "superadmin",
        "admin",
        "owner",
        "role!@#",
        "a" * 51,
    ]

    for bad_name in invalid_names:
        res = client.post(
            "/api/v1/roles",
            headers=owner_headers,
            json={"name": bad_name, "permissions": ["products:read"]},
        )
        assert res.status_code in (409, 422), f"Expected 409 or 422 for name '{bad_name}', got {res.status_code}: {res.text}"

    # 3. Test invalid permissions (e.g. ["string"] reported by tester) -> MUST BE 422
    invalid_permissions_payloads = [
        ["string"],
        [""],
        ["   "],
        ["random:unknown"],
        ["products:read", "string"],
        ["hack:all"],
    ]

    for bad_perms in invalid_permissions_payloads:
        res = client.post(
            "/api/v1/roles",
            headers=owner_headers,
            json={"name": "custom_lead", "permissions": bad_perms},
        )
        assert res.status_code == 422, f"Expected 422 for perms {bad_perms}, got {res.status_code}: {res.text}"
        detail_text = res.text
        assert "Invalid permission" in detail_text or "cannot be empty" in detail_text

    # 4. Test valid custom role creation succeeds with 201
    valid_create_res = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={
            "name": "shift_supervisor",
            "permissions": ["products:read", "inventory:read", "pos:shift_manage"],
        },
    )
    assert valid_create_res.status_code == 201
    created_role = valid_create_res.json()
    role_id = created_role["id"]
    assert created_role["name"] == "shift_supervisor"
    assert "pos:shift_manage" in created_role["permissions"]

    # 5. Test PATCH /api/v1/roles/{role_id} with invalid name -> MUST BE 422
    patch_bad_name = client.patch(
        f"/api/v1/roles/{role_id}",
        headers=owner_headers,
        json={"name": "000"},
    )
    assert patch_bad_name.status_code == 422

    # 6. Test PATCH /api/v1/roles/{role_id} with invalid permissions -> MUST BE 422
    patch_bad_perms = client.patch(
        f"/api/v1/roles/{role_id}",
        headers=owner_headers,
        json={"permissions": ["string"]},
    )
    assert patch_bad_perms.status_code == 422

    # 7. Test PATCH /api/v1/roles/{role_id} with valid updates -> 200
    patch_valid = client.patch(
        f"/api/v1/roles/{role_id}",
        headers=owner_headers,
        json={"name": "senior_supervisor", "permissions": ["products:read", "inventory:read"]},
    )
    assert patch_valid.status_code == 200
    assert patch_valid.json()["name"] == "senior_supervisor"
    assert patch_valid.json()["permissions"] == ["products:read", "inventory:read"]

    # 8. Test GET /api/v1/roles/permissions returns complete list with descriptions
    perms_res = client.get("/api/v1/roles/permissions", headers=owner_headers)
    assert perms_res.status_code == 200
    groups = perms_res.json()
    all_codes = {p["code"] for g in groups for p in g["permissions"]}
    assert "pos:shift_manage" in all_codes
    assert "payments:read" in all_codes
    assert "dashboard:view" in all_codes
    assert "billing:read" in all_codes
    assert "inventory:read" in all_codes

    # 9. Test path parameter validation for role_id
    assert client.get("/api/v1/roles/0", headers=owner_headers).status_code == 422
    assert client.get("/api/v1/roles/-1", headers=owner_headers).status_code == 422
    assert client.get("/api/v1/roles/1000000", headers=owner_headers).status_code == 422

    # 10. Clean up: Delete created role
    del_res = client.delete(f"/api/v1/roles/{role_id}", headers=owner_headers)
    assert del_res.status_code == 200

