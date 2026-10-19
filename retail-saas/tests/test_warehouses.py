import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.models.store_transfer import StoreTransfer
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"wh-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Warehouse Co {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Admin",
            "password": "Password123!",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    tenant_id = user.tenant_id

    # Create a store for linking
    store = Store(
        tenant_id=tenant_id,
        name=f"Hub Store {slug[:4]}",
        code=f"HUB-{slug[:4].upper()}",
        is_active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    store_id = store.id
    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store_id,
        "slug": slug,
    }


def test_create_warehouse_success(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]

    code = f"WH-{uuid.uuid4().hex[:6].upper()}"
    resp = client.post(
        "/api/v1/warehouses",
        json={
            "name": "Central Distribution Hub",
            "code": code,
            "address": "Plot 45, Industrial Zone, Pune",
            "store_id": store_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Central Distribution Hub"
    assert data["code"] == code
    assert data["store_id"] == store_id
    assert data["store_name"] is not None
    assert data["is_active"] is True
    assert data["id"] > 0


def test_create_warehouse_validations(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Invalid name (too short)
    res1 = client.post(
        "/api/v1/warehouses",
        json={"name": "A", "code": "WH-VAL1"},
        headers=headers,
    )
    assert res1.status_code == 422

    # Invalid name ("string" placeholder)
    res2 = client.post(
        "/api/v1/warehouses",
        json={"name": "string", "code": "WH-VAL2"},
        headers=headers,
    )
    assert res2.status_code == 422

    # Invalid code (special characters like @, #)
    res3 = client.post(
        "/api/v1/warehouses",
        json={"name": "Valid Name", "code": "WH@#$"},
        headers=headers,
    )
    assert res3.status_code == 422

    # Invalid store_id (negative)
    res4 = client.post(
        "/api/v1/warehouses",
        json={"name": "Valid Name", "code": "WH-VAL4", "store_id": -1},
        headers=headers,
    )
    assert res4.status_code == 422


def test_create_warehouse_duplicate_code(tenant_fixture):
    headers = tenant_fixture["headers"]
    code = f"DUP-{uuid.uuid4().hex[:6].upper()}"

    res1 = client.post(
        "/api/v1/warehouses",
        json={"name": "Warehouse Alpha", "code": code},
        headers=headers,
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/api/v1/warehouses",
        json={"name": "Warehouse Beta", "code": code},
        headers=headers,
    )
    assert res2.status_code == 409
    assert "already exists" in res2.text.lower()


def test_create_warehouse_cross_tenant_store(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    # Register Tenant B
    slug_b = f"whb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Tenant B creates a store
    db = SessionLocal()
    user_b = db.query(User).filter(User.email == email_b).first()
    store_b = Store(tenant_id=user_b.tenant_id, name="Store B", code="SB-01", is_active=True)
    db.add(store_b)
    db.commit()
    db.refresh(store_b)
    store_b_id = store_b.id
    db.close()

    # Tenant A attempts to link Tenant B's store -> 404 Store not found
    resp = client.post(
        "/api/v1/warehouses",
        json={
            "name": "Intruder Warehouse",
            "code": f"WH-SEC-{uuid.uuid4().hex[:4].upper()}",
            "store_id": store_b_id,
        },
        headers=headers_a,
    )
    assert resp.status_code == 404, resp.text
    assert "store not found" in resp.text.lower()


def test_list_warehouses_filters_and_pagination(tenant_fixture):
    headers = tenant_fixture["headers"]
    unique_prefix = f"FLT-{uuid.uuid4().hex[:4].upper()}"

    # Create 3 warehouses
    client.post(
        "/api/v1/warehouses",
        json={"name": f"{unique_prefix} Alpha Hub", "code": f"{unique_prefix}-01"},
        headers=headers,
    )
    w2 = client.post(
        "/api/v1/warehouses",
        json={"name": f"{unique_prefix} Beta Depot", "code": f"{unique_prefix}-02"},
        headers=headers,
    ).json()
    # Deactivate w2
    client.patch(f"/api/v1/warehouses/{w2['id']}/status", json={"is_active": False}, headers=headers)

    # 1. Search by name
    res_search = client.get(f"/api/v1/warehouses?search={unique_prefix} Alpha", headers=headers)
    assert res_search.status_code == 200
    items = res_search.json()
    assert len(items) == 1
    assert items[0]["name"] == f"{unique_prefix} Alpha Hub"

    # 2. Filter by is_active=false
    res_inactive = client.get(f"/api/v1/warehouses?is_active=false&search={unique_prefix}", headers=headers)
    assert res_inactive.status_code == 200
    items_in = res_inactive.json()
    assert len(items_in) == 1
    assert items_in[0]["code"] == f"{unique_prefix}-02"

    # 3. Pagination
    res_page = client.get(f"/api/v1/warehouses?search={unique_prefix}&page=1&page_size=1", headers=headers)
    assert res_page.status_code == 200
    assert len(res_page.json()) == 1


def test_get_warehouse_details(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]

    create_res = client.post(
        "/api/v1/warehouses",
        json={
            "name": "Regional Hub",
            "code": f"REG-{uuid.uuid4().hex[:4].upper()}",
            "store_id": store_id,
        },
        headers=headers,
    ).json()

    res = client.get(f"/api/v1/warehouses/{create_res['id']}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == create_res["id"]
    assert data["name"] == "Regional Hub"
    assert data["store_id"] == store_id
    assert data["store_name"] is not None

    # 404 for nonexistent
    assert client.get("/api/v1/warehouses/999999", headers=headers).status_code == 404

    # 422 for invalid path
    assert client.get("/api/v1/warehouses/0", headers=headers).status_code == 422
    assert client.get("/api/v1/warehouses/-5", headers=headers).status_code == 422


def test_update_warehouse_and_address_null(tenant_fixture):
    headers = tenant_fixture["headers"]

    w = client.post(
        "/api/v1/warehouses",
        json={
            "name": "Update Target WH",
            "code": f"UPD-{uuid.uuid4().hex[:4].upper()}",
            "address": "Initial Address 123",
        },
        headers=headers,
    ).json()

    # 1. Update name and address
    res1 = client.patch(
        f"/api/v1/warehouses/{w['id']}",
        json={"name": "Renamed WH", "address": "New Address 456"},
        headers=headers,
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["name"] == "Renamed WH"
    assert res1.json()["address"] == "New Address 456"

    # 2. Update address with None / null (Verified bug fix: should succeed, not 422)
    res2 = client.patch(
        f"/api/v1/warehouses/{w['id']}",
        json={"address": None},
        headers=headers,
    )
    assert res2.status_code == 200, res2.text
    assert res2.json()["address"] is None


def test_update_warehouse_status_toggle(tenant_fixture):
    headers = tenant_fixture["headers"]

    w = client.post(
        "/api/v1/warehouses",
        json={"name": "Status Target WH", "code": f"ST-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    ).json()
    assert w["is_active"] is True

    # 1. Deactivate via boolean
    res1 = client.patch(f"/api/v1/warehouses/{w['id']}/status", json={"is_active": False}, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["is_active"] is False

    # 2. Activate via string "active"
    res2 = client.patch(f"/api/v1/warehouses/{w['id']}/status", json={"status": "active"}, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["is_active"] is True

    # 3. Invalid status -> 422
    res3 = client.patch(f"/api/v1/warehouses/{w['id']}/status", json={"status": "invalid"}, headers=headers)
    assert res3.status_code == 422


def test_warehouse_dashboard(tenant_fixture):
    headers = tenant_fixture["headers"]

    res = client.get("/api/v1/warehouses/dashboard", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_warehouses" in data
    assert "active_warehouses" in data
    assert "inactive_warehouses" in data
    assert "total_stock_units" in data
    assert "total_stock_value" in data
    assert data["total_warehouses"] >= 0


def test_warehouse_stock_endpoint(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]
    store_id = tenant_fixture["store_id"]

    # Create warehouse linked to store
    w = client.post(
        "/api/v1/warehouses",
        json={
            "name": "Stocked Warehouse",
            "code": f"STK-{uuid.uuid4().hex[:4].upper()}",
            "store_id": store_id,
        },
        headers=headers,
    ).json()

    # Add product and inventory in database
    db = SessionLocal()
    cat = Category(tenant_id=tenant_id, name="Electronics")
    db.add(cat)
    db.commit()
    db.refresh(cat)

    prod = Product(
        tenant_id=tenant_id,
        category_id=cat.id,
        name="Smart Tablet 10",
        sku=f"TAB-{uuid.uuid4().hex[:4].upper()}",
        price=Decimal("15000.00"),
        cost_price=Decimal("12000.00"),
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)

    inv = Inventory(
        tenant_id=tenant_id,
        store_id=store_id,
        product_id=prod.id,
        quantity=Decimal("25.0000"),
        min_stock_level=5,
    )
    db.add(inv)
    db.commit()
    db.close()

    # Query GET /warehouses/{warehouse_id}/stock
    stock_res = client.get(f"/api/v1/warehouses/{w['id']}/stock", headers=headers)
    assert stock_res.status_code == 200, stock_res.text
    stock_data = stock_res.json()
    assert stock_data["success"] is True
    assert stock_data["warehouse_id"] == w["id"]
    assert stock_data["total_items"] >= 1
    assert Decimal(str(stock_data["total_quantity"])) >= 25
    assert Decimal(str(stock_data["total_stock_value"])) >= 300000

    # Test search within warehouse stock
    search_res = client.get(f"/api/v1/warehouses/{w['id']}/stock?search=Smart Tablet", headers=headers)
    assert search_res.status_code == 200
    assert len(search_res.json()["data"]) == 1
    assert search_res.json()["data"][0]["product_name"] == "Smart Tablet 10"


def test_warehouse_transfers_endpoint(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]
    store_id = tenant_fixture["store_id"]

    # Create destination store
    db = SessionLocal()
    dest_store = Store(tenant_id=tenant_id, name="Outlet Store Pune", is_active=True)
    db.add(dest_store)
    db.commit()
    db.refresh(dest_store)
    dest_store_id = dest_store.id

    # Create warehouse linked to store_id
    w = client.post(
        "/api/v1/warehouses",
        json={"name": "Logistics WH", "code": f"LOG-{uuid.uuid4().hex[:4].upper()}", "store_id": store_id},
        headers=headers,
    ).json()

    # Create store transfer
    st = StoreTransfer(
        transfer_number=f"TR-{uuid.uuid4().hex[:6].upper()}",
        source_store_id=store_id,
        destination_store_id=dest_store_id,
        status="Dispatched",
    )
    db.add(st)
    db.commit()
    db.close()

    tr_res = client.get(f"/api/v1/warehouses/{w['id']}/transfers", headers=headers)
    assert tr_res.status_code == 200, tr_res.text
    tr_data = tr_res.json()
    assert tr_data["success"] is True
    assert tr_data["total_transfers"] >= 1
    transfer_obj = tr_data["data"][0]
    assert transfer_obj["transfer_type"] == "outbound"
    assert transfer_obj["source_store_id"] == store_id
    assert transfer_obj["destination_store_id"] == dest_store_id


def test_delete_warehouse_active_stock_protection_and_success(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]
    store_id = tenant_fixture["store_id"]

    # 1. Create empty warehouse and delete
    w_empty = client.post(
        "/api/v1/warehouses",
        json={"name": "Empty Disposable WH", "code": f"EMP-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    ).json()

    del_res = client.delete(f"/api/v1/warehouses/{w_empty['id']}", headers=headers)
    assert del_res.status_code == 200, del_res.text
    assert del_res.json()["success"] is True
    assert "deleted successfully" in del_res.json()["message"]

    # Verify 404 after deletion
    assert client.get(f"/api/v1/warehouses/{w_empty['id']}", headers=headers).status_code == 404

    # 2. Create warehouse linked to store with active stock -> deletion blocked
    w_stocked = client.post(
        "/api/v1/warehouses",
        json={"name": "Stock Protected WH", "code": f"PRT-{uuid.uuid4().hex[:4].upper()}", "store_id": store_id},
        headers=headers,
    ).json()

    db = SessionLocal()
    prod = Product(
        tenant_id=tenant_id,
        name="Protected Item",
        sku=f"PRT-{uuid.uuid4().hex[:4].upper()}",
        price=Decimal("100.00"),
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)

    inv = Inventory(tenant_id=tenant_id, store_id=store_id, product_id=prod.id, quantity=Decimal("10.00"))
    db.add(inv)
    db.commit()
    db.close()

    del_blocked = client.delete(f"/api/v1/warehouses/{w_stocked['id']}", headers=headers)
    assert del_blocked.status_code == 409, del_blocked.text
    assert "active stock" in del_blocked.text.lower()


def test_warehouse_cross_tenant_isolation(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    # Register Tenant B
    slug_b = f"whsec-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Tenant B creates a warehouse
    wb = client.post(
        "/api/v1/warehouses",
        json={"name": "Tenant B Vault", "code": f"SEC-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers_b,
    ).json()
    wb_id = wb["id"]

    # Tenant A tries to GET -> 404
    assert client.get(f"/api/v1/warehouses/{wb_id}", headers=headers_a).status_code == 404

    # Tenant A tries to PATCH -> 404
    assert client.patch(f"/api/v1/warehouses/{wb_id}", json={"name": "Hacked WH"}, headers=headers_a).status_code == 404

    # Tenant A tries to DELETE -> 404
    assert client.delete(f"/api/v1/warehouses/{wb_id}", headers=headers_a).status_code == 404

    # Tenant A tries to view stock -> 404
    assert client.get(f"/api/v1/warehouses/{wb_id}/stock", headers=headers_a).status_code == 404


def test_warehouse_create_valid_and_invalid_address(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Valid warehouse creation
    valid_payload = {
        "name": "Central Hub Pune",
        "code": "WH-PUN-01",
        "address": "Plot 42, MIDC Bhosari, Pune, Maharashtra",
    }
    resp = client.post("/api/v1/warehouses", json=valid_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Central Hub Pune"
    assert created["code"] == "WH-PUN-01"
    assert created["address"] == "Plot 42, MIDC Bhosari, Pune, Maharashtra"

    # Invalid addresses that must be rejected (422)
    invalid_addresses = [
        "1234",          # Reported in screenshot: purely numeric short address
        "12345",         # purely numeric
        "99999999",      # numeric only
        "####",          # special chars only
        "aaaaa",         # repeating single char
        "test",          # placeholder
        "string",        # placeholder
        "dummy",         # placeholder
        "   ",           # whitespace
    ]
    for bad_addr in invalid_addresses:
        bad_payload = {
            "name": "Valid Warehouse Name",
            "code": f"WH-{uuid.uuid4().hex[:4].upper()}",
            "address": bad_addr,
        }
        res = client.post("/api/v1/warehouses", json=bad_payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for address '{bad_addr}', got {res.status_code}: {res.text}"


def test_warehouse_create_invalid_name_and_code(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Invalid names
    for bad_name in ["ppp", "12345", "string", "test", ""]:
        res = client.post(
            "/api/v1/warehouses",
            json={
                "name": bad_name,
                "code": f"WH-{uuid.uuid4().hex[:4].upper()}",
            },
            headers=headers,
        )
        assert res.status_code == 422, f"Expected 422 for name '{bad_name}', got {res.status_code}: {res.text}"

    # Invalid codes
    for bad_code in ["00000", "12345", "string", ""]:
        res = client.post(
            "/api/v1/warehouses",
            json={
                "name": "Valid Warehouse",
                "code": bad_code,
            },
            headers=headers,
        )
        assert res.status_code == 422, f"Expected 422 for code '{bad_code}', got {res.status_code}: {res.text}"


def test_warehouse_patch_invalid_json_expected_value_message(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Create warehouse first
    resp = client.post(
        "/api/v1/warehouses",
        json={
            "name": "West Coast Warehouse",
            "code": "WH-WEST-01",
            "address": "Gala No 5, Highway Hub, Mumbai",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    wh_id = resp.json()["id"]

    # 1. QA reported: PATCH with unquoted is_active: fdf
    bad_json_resp = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        content=b'{\n  "is_active": fdf\n}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert bad_json_resp.status_code == 422, bad_json_resp.text
    data = bad_json_resp.json()
    assert data["errors"][0]["field"] == "is_active"
    assert "Expected a boolean: true or false" in data["message"]

    # 2. QA reported: PATCH with missing value: "is_active":
    bad_json_resp2 = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        content=b'{\n  "is_active": \n}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert bad_json_resp2.status_code == 422, bad_json_resp2.text
    data2 = bad_json_resp2.json()
    assert data2["errors"][0]["field"] == "is_active"
    assert "Expected a boolean: true or false" in data2["message"]

    # 3. PATCH with invalid address: "1234"
    bad_addr_resp = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        json={"address": "1234"},
        headers=headers,
    )
    assert bad_addr_resp.status_code == 422

    # 4. Valid PATCH
    good_patch = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        json={"name": "Renamed Coast Warehouse", "is_active": False},
        headers=headers,
    )
    assert good_patch.status_code == 200
    assert good_patch.json()["name"] == "Renamed Coast Warehouse"
    assert good_patch.json()["is_active"] is False
