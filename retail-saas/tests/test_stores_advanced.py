import uuid
import pytest
from decimal import Decimal
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


def test_inactive_store_get_and_patch_consistency():
    """Verify that when a store is deactivated, GET /stores/{id} returns 200 OK (not 404)."""
    tenant = create_tenant_and_admin("storeinact")
    headers = tenant["headers"]

    # 1. Create a store
    store_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": "Bandra Retail Outlet",
            "code": f"BND-{uuid.uuid4().hex[:4].upper()}",
            "address": "Linking Road, Bandra West",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400050",
            "phone": "9820011223",
        },
        headers=headers,
    )
    assert store_resp.status_code == 201, store_resp.text
    store_id = store_resp.json()["id"]

    # Verify pincode and phone are strings, not 0
    assert store_resp.json()["pincode"] == "400050"
    assert store_resp.json()["phone"] == "9820011223"

    # 2. Deactivate the store via PATCH
    patch_resp = client.patch(
        f"/api/v1/stores/{store_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["is_active"] is False

    # 3. GET the deactivated store (previously failed with 404!)
    get_resp = client.get(
        f"/api/v1/stores/{store_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["id"] == store_id
    assert get_resp.json()["is_active"] is False
    assert get_resp.json()["pincode"] == "400050"


def test_list_stores_filters():
    """Verify list_stores with include_inactive, search, and is_warehouse."""
    tenant = create_tenant_and_admin("storefilters")
    headers = tenant["headers"]

    # Create Store 1: Mumbai active retail
    s1 = client.post(
        "/api/v1/stores/",
        json={
            "name": "Mumbai Superstore",
            "code": f"MUM-{uuid.uuid4().hex[:4].upper()}",
            "address": "Dadar West",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400028",
            "is_main": True,
        },
        headers=headers,
    ).json()

    # Create Store 2: Pune active warehouse
    s2 = client.post(
        "/api/v1/stores/",
        json={
            "name": "Pune Central Depot",
            "code": f"PUN-{uuid.uuid4().hex[:4].upper()}",
            "address": "Hadapsar Industrial Estate",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411028",
            "is_main": False,
        },
        headers=headers,
    ).json()

    # Create Store 3: Nashik deactivated store
    s3 = client.post(
        "/api/v1/stores/",
        json={
            "name": "Nashik Branch",
            "code": f"NSK-{uuid.uuid4().hex[:4].upper()}",
            "address": "College Road",
            "city": "Nashik",
            "state": "Maharashtra",
            "pincode": "422005",
            "is_main": False,
        },
        headers=headers,
    ).json()
    client.patch(f"/api/v1/stores/{s3['id']}", json={"is_active": False}, headers=headers)

    # By default, list_stores excludes inactive
    list_active = client.get("/api/v1/stores/", headers=headers).json()
    active_ids = [s["id"] for s in list_active]
    assert s1["id"] in active_ids
    assert s2["id"] in active_ids
    assert s3["id"] not in active_ids

    # With include_inactive=true, all 3 are returned
    list_all = client.get("/api/v1/stores/?include_inactive=true", headers=headers).json()
    all_ids = [s["id"] for s in list_all]
    assert s3["id"] in all_ids

    # Search by city 'pune'
    search_pune = client.get("/api/v1/stores/?search=pune", headers=headers).json()
    assert len(search_pune) == 1
    assert search_pune[0]["id"] == s2["id"]

    # Filter is_warehouse=false (i.e. is_main=True)
    retail_stores = client.get("/api/v1/stores/?is_warehouse=false", headers=headers).json()
    retail_ids = [s["id"] for s in retail_stores]
    assert s1["id"] in retail_ids
    assert s2["id"] not in retail_ids


def test_set_main_store_and_activation_endpoints():
    """Test POST /stores/{id}/set-main, PATCH /stores/{id}/activate, and /deactivate."""
    tenant = create_tenant_and_admin("storemain")
    headers = tenant["headers"]

    # Store A (Initial Main)
    sa = client.post(
        "/api/v1/stores/",
        json={"name": "Head Branch Alpha", "code": f"HBA-{uuid.uuid4().hex[:4].upper()}", "is_main": True},
        headers=headers,
    ).json()

    # Store B (Secondary)
    sb = client.post(
        "/api/v1/stores/",
        json={"name": "Branch Beta", "code": f"BBB-{uuid.uuid4().hex[:4].upper()}", "is_main": False},
        headers=headers,
    ).json()

    # Promote Store B to Main Store
    set_main_res = client.post(f"/api/v1/stores/{sb['id']}/set-main", headers=headers)
    assert set_main_res.status_code == 200, set_main_res.text
    data = set_main_res.json()
    assert data["success"] is True
    assert data["store_id"] == sb["id"]
    assert data["previous_main_store_id"] == sa["id"]

    # Verify Store A is now NOT main, and Store B is main
    get_sa = client.get(f"/api/v1/stores/{sa['id']}", headers=headers).json()
    get_sb = client.get(f"/api/v1/stores/{sb['id']}", headers=headers).json()
    assert get_sa["is_main"] is False
    assert get_sb["is_main"] is True

    # Attempt to deactivate main store -> Expect 409 Conflict
    deact_main = client.patch(f"/api/v1/stores/{sb['id']}/deactivate", headers=headers)
    assert deact_main.status_code == 409
    assert "Cannot deactivate the main store" in deact_main.text

    # Deactivate Store A -> 200 OK
    deact_a = client.patch(f"/api/v1/stores/{sa['id']}/deactivate", headers=headers)
    assert deact_a.status_code == 200
    assert deact_a.json()["is_active"] is False

    # Attempt to set deactivated store as main -> Expect 409 Conflict
    fail_set = client.post(f"/api/v1/stores/{sa['id']}/set-main", headers=headers)
    assert fail_set.status_code == 409
    assert "Cannot set an inactive store as main store" in fail_set.text

    # Reactivate Store A -> 200 OK
    act_a = client.patch(f"/api/v1/stores/{sa['id']}/activate", headers=headers)
    assert act_a.status_code == 200
    assert act_a.json()["is_active"] is True


def test_store_staff_and_isolation():
    """Test GET /stores/{id}/staff and role permissions."""
    tenant = create_tenant_and_admin("storestaff")
    headers = tenant["headers"]

    # Create Store 1 & Store 2
    s1 = client.post(
        "/api/v1/stores/",
        json={"name": "Kothrud Store", "code": f"KOT-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    ).json()

    s2 = client.post(
        "/api/v1/stores/",
        json={"name": "Aundh Store", "code": f"AUN-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    ).json()

    # Create Manager assigned to Store 1
    mgr_email = f"mgr-{uuid.uuid4().hex[:6]}@test.com"
    mgr_user = client.post(
        "/api/v1/users",
        json={
            "email": mgr_email,
            "full_name": "Kothrud Manager",
            "password": "Password123!",
            "role": "manager",
            "phone": "9812345678",
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/users/{mgr_user['id']}/assign-store", json={"store_id": s1["id"]}, headers=headers)

    # Get staff for Store 1 as Store Owner
    staff_res = client.get(f"/api/v1/stores/{s1['id']}/staff", headers=headers)
    assert staff_res.status_code == 200
    staff_data = staff_res.json()
    assert staff_data["total_staff"] >= 1
    emails = [m["email"] for m in staff_data["staff"]]
    assert mgr_email in emails

    # Login as Store Manager
    mgr_login = client.post(
        "/api/v1/auth/login",
        json={"email": mgr_email, "password": "Password123!"},
    ).json()
    mgr_headers = {"Authorization": f"Bearer {mgr_login['access_token']}"}

    # Store Manager can view their own store staff
    own_staff = client.get(f"/api/v1/stores/{s1['id']}/staff", headers=mgr_headers)
    assert own_staff.status_code == 200
    assert own_staff.json()["store_id"] == s1["id"]

    # Store Manager cannot view other store's staff (Store 2) -> Expect 403 Forbidden
    other_staff = client.get(f"/api/v1/stores/{s2['id']}/staff", headers=mgr_headers)
    assert other_staff.status_code == 403
    assert "Access denied to this store" in other_staff.text


def test_store_summary_and_inventory_summary():
    """Test GET /stores/{id}/summary and /inventory-summary."""
    tenant = create_tenant_and_admin("storesummary")
    headers = tenant["headers"]

    # Create store
    store = client.post(
        "/api/v1/stores/",
        json={"name": "Vashi Mega Mall", "code": f"VSH-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    ).json()
    store_id = store["id"]

    # 1. Summary API
    summary_res = client.get(f"/api/v1/stores/{store_id}/summary", headers=headers)
    assert summary_res.status_code == 200, summary_res.text
    summary = summary_res.json()
    assert summary["store_id"] == store_id
    assert summary["store_name"] == "Vashi Mega Mall"
    assert "today_sales_amount" in summary
    assert "today_orders_count" in summary
    assert "total_orders_count" in summary
    assert "total_staff_count" in summary
    assert "active_pos_shifts_count" in summary
    assert "low_stock_items_count" in summary

    # 2. Inventory Summary API
    inv_res = client.get(f"/api/v1/stores/{store_id}/inventory-summary", headers=headers)
    assert inv_res.status_code == 200, inv_res.text
    inv_data = inv_res.json()
    assert inv_data["store_id"] == store_id
    assert inv_data["total_skus"] == 0
    assert inv_data["total_stock_quantity"] == 0.0 or inv_data["total_stock_quantity"] == "0.00"
    assert inv_data["total_stock_value"] == 0.0 or inv_data["total_stock_value"] == "0.00"
    assert inv_data["in_stock_skus"] == 0
    assert inv_data["low_stock_skus"] == 0
    assert inv_data["out_of_stock_skus"] == 0


def test_delete_store_typed_response():
    """Test DELETE /stores/{id} returns typed StoreDeleteResponse."""
    tenant = create_tenant_and_admin("storedel")
    headers = tenant["headers"]

    # Create store to delete
    store = client.post(
        "/api/v1/stores/",
        json={"name": "Temporary Store", "code": f"TMP-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    ).json()
    store_id = store["id"]

    # Delete store
    del_res = client.delete(f"/api/v1/stores/{store_id}", headers=headers)
    assert del_res.status_code == 200, del_res.text
    del_data = del_res.json()
    assert del_data["success"] is True
    assert del_data["message"] == "Store deleted successfully"
    assert del_data["store_id"] == store_id
