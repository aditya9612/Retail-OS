import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_tenant_and_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {slug}",
            "domain": slug,
            "owner_email": email,
            "owner_name": f"Admin {prefix}",
            "password": "Password123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
    }


def test_remove_user_from_store_flow():
    tenant_info = create_tenant_and_admin("removestore")
    headers = tenant_info["headers"]

    # 1. Create a store
    store_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": "Main Branch",
            "code": f"STR-{uuid.uuid4().hex[:4].upper()}",
            "address_line1": "123 High Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
        },
        headers=headers,
    )
    assert store_resp.status_code == 201, store_resp.text
    store_id = store_resp.json()["id"]

    # 2. Create another store
    store2_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": "Second Branch",
            "code": f"STR2-{uuid.uuid4().hex[:4].upper()}",
            "address_line1": "456 Market Road",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
        },
        headers=headers,
    )
    assert store2_resp.status_code == 201, store2_resp.text
    store2_id = store2_resp.json()["id"]

    # 3. Create a user (store_id is removed from creation, so user starts unassigned)
    user_email = f"staff-{uuid.uuid4().hex[:6]}@test.com"
    user_resp = client.post(
        "/api/v1/users",
        json={
            "email": user_email,
            "full_name": "Test Staff",
            "password": "Password123!",
            "role": "staff",
        },
        headers=headers,
    )
    assert user_resp.status_code == 201, user_resp.text
    user_id = user_resp.json()["id"]
    assert user_resp.json()["store_id"] is None

    # Assign user to store 1
    assign_resp = client.post(
        f"/api/v1/users/{user_id}/assign-store",
        json={"store_id": store_id},
        headers=headers,
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["store_id"] == store_id

    # 4. Try removing user from wrong store_id (store2_id) -> Expect 409 Conflict
    mismatch_resp = client.post(
        f"/api/v1/users/{user_id}/remove-store",
        json={"store_id": store2_id},
        headers=headers,
    )
    assert mismatch_resp.status_code == 409, mismatch_resp.text
    assert f"User is assigned to store {store_id}, not store {store2_id}" in str(mismatch_resp.json())

    # 5. Remove user from store with matching store_id -> Expect 200 OK
    remove_resp = client.post(
        f"/api/v1/users/{user_id}/remove-store",
        json={"store_id": store_id},
        headers=headers,
    )
    assert remove_resp.status_code == 200, remove_resp.text
    data = remove_resp.json()
    assert data["message"] == "User removed from store successfully"
    assert data["user_id"] == user_id
    assert data["store_id"] is None
    assert data["previous_store_id"] == store_id

    # Verify user in database now has store_id = None
    get_user_resp = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert get_user_resp.status_code == 200
    assert get_user_resp.json()["store_id"] is None

    # 6. Try removing again when user is already not assigned to any store -> Expect 409 Conflict
    already_removed_resp = client.post(
        f"/api/v1/users/{user_id}/remove-store",
        json={"store_id": store_id},
        headers=headers,
    )
    assert already_removed_resp.status_code == 409, already_removed_resp.text
    assert "User is not currently assigned to any store" in str(already_removed_resp.json())

    # 7. Re-assign user to store2
    assign_resp = client.post(
        f"/api/v1/users/{user_id}/assign-store",
        json={"store_id": store2_id},
        headers=headers,
    )
    assert assign_resp.status_code == 200, assign_resp.text
    assert assign_resp.json()["store_id"] == store2_id

    # 8. Remove user without passing store_id in body (generic remove) -> Expect 200 OK
    remove_no_body_resp = client.post(
        f"/api/v1/users/{user_id}/remove-store",
        headers=headers,
    )
    assert remove_no_body_resp.status_code == 200, remove_no_body_resp.text
    data2 = remove_no_body_resp.json()
    assert data2["previous_store_id"] == store2_id
    assert data2["store_id"] is None

    # 9. Body store_id test: Assign to store 1 again and remove with body store_id
    client.post(
        f"/api/v1/users/{user_id}/assign-store",
        json={"store_id": store_id},
        headers=headers,
    )
    remove_body_resp = client.post(
        f"/api/v1/users/{user_id}/remove-store",
        json={"store_id": store_id},
        headers=headers,
    )
    assert remove_body_resp.status_code == 200, remove_body_resp.text
    assert remove_body_resp.json()["previous_store_id"] == store_id

