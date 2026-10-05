from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_context(unique_slug):
    email = f"inv-{unique_slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "InventoryTest",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Inv Admin",
            "password": "testpass123",
        },
    )
    assert reg_resp.status_code in (200, 201)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create Store 1
    store1 = client.post(
        "/api/v1/stores",
        json={"name": "Store Alpha", "code": f"SA-{unique_slug[:4]}"},
        headers=headers,
    ).json()

    # Create Store 2
    store2 = client.post(
        "/api/v1/stores",
        json={"name": "Store Beta", "code": f"SB-{unique_slug[:4]}"},
        headers=headers,
    ).json()

    # Create Product
    product = client.post(
        "/api/v1/products",
        json={
            "name": "Widget A",
            "sku": f"WGT-{unique_slug}",
            "price": "100.00",
            "cost_price": "60.00",
            "gst_rate": "18.00",
        },
        headers=headers,
    ).json()

    return {
        "headers": headers,
        "store1": store1,
        "store2": store2,
        "product": product,
    }


# ==================== STOCK IN TESTS ====================

def test_stock_in_success(auth_context):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": store_id,
            "product_id": product_id,
            "quantity": 100,
            "batch_number": "BATCH-2026-A",
            "unit_cost": "60.00",
            "notes": "Initial stock receipt",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["quantity"] == 100
    assert data["previous_stock"] == 0
    assert data["new_stock"] == 100
    assert data["reference"] is not None
    assert data["reference"].startswith("IN-")
    assert data["notes"] == "Initial stock receipt"

    # Verify inventory record
    inv_resp = client.get(f"/api/v1/inventory/{product_id}", headers=headers)
    assert inv_resp.status_code == 200
    assert inv_resp.json()["quantity"] == 100


def test_stock_in_accumulates_quantity(auth_context):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    # First stock-in
    r1 = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 50},
        headers=headers,
    )
    assert r1.status_code == 201
    assert r1.json()["new_stock"] == 50

    # Second stock-in
    r2 = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 100},
        headers=headers,
    )
    assert r2.status_code == 201
    assert r2.json()["previous_stock"] == 50
    assert r2.json()["new_stock"] == 150

    inv_resp = client.get(f"/api/v1/inventory/{product_id}", headers=headers)
    assert inv_resp.json()["quantity"] == 150


@pytest.mark.parametrize("invalid_batch", ["", "   ", "string", "test", "----", "!@#$", "@#$%", "..."])
def test_stock_in_rejects_invalid_batch(auth_context, invalid_batch):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": store_id,
            "product_id": product_id,
            "quantity": 10,
            "batch_number": invalid_batch,
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("invalid_cost", [0, -10, "-5.00", 0.00])
def test_stock_in_rejects_invalid_unit_cost(auth_context, invalid_cost):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": store_id,
            "product_id": product_id,
            "quantity": 10,
            "unit_cost": invalid_cost,
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("invalid_notes", ["", "   ", "string", "test", "----", "!@#$"])
def test_stock_in_rejects_invalid_notes(auth_context, invalid_notes):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": store_id,
            "product_id": product_id,
            "quantity": 10,
            "notes": invalid_notes,
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_stock_in_rejects_nonexistent_ids(auth_context):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    # Nonexistent product
    r1 = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": 999999, "quantity": 10},
        headers=headers,
    )
    assert r1.status_code == 404

    # Nonexistent store
    r2 = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": 999999, "product_id": product_id, "quantity": 10},
        headers=headers,
    )
    assert r2.status_code == 404


# ==================== STOCK OUT TESTS ====================

def test_stock_out_success(auth_context):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    # Stock in 100
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 100},
        headers=headers,
    )

    # Stock out 30
    resp = client.post(
        "/api/v1/inventory/stock-out",
        json={
            "store_id": store_id,
            "product_id": product_id,
            "quantity": 30,
            "notes": "Sold in store",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["quantity"] == 30
    assert data["previous_stock"] == 100
    assert data["new_stock"] == 70
    assert data["reference"] is not None
    assert data["reference"].startswith("OUT-")

    inv = client.get(f"/api/v1/inventory/{product_id}", headers=headers).json()
    assert inv["quantity"] == 70


def test_stock_out_insufficient_stock(auth_context):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    # Stock in 20
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 20},
        headers=headers,
    )

    # Try stock out 50
    resp = client.post(
        "/api/v1/inventory/stock-out",
        json={"store_id": store_id, "product_id": product_id, "quantity": 50},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Insufficient stock" in resp.text


@pytest.mark.parametrize("invalid_notes", ["", "   ", "string", "----", "!@#$"])
def test_stock_out_rejects_invalid_notes(auth_context, invalid_notes):
    headers = auth_context["headers"]
    store_id = auth_context["store1"]["id"]
    product_id = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/stock-out",
        json={
            "store_id": store_id,
            "product_id": product_id,
            "quantity": 5,
            "notes": invalid_notes,
        },
        headers=headers,
    )
    assert resp.status_code == 422


# ==================== STOCK TRANSFER TESTS ====================

def test_stock_transfer_success(auth_context):
    headers = auth_context["headers"]
    s1 = auth_context["store1"]["id"]
    s2 = auth_context["store2"]["id"]
    p = auth_context["product"]["id"]

    # Stock in 100 in Store 1
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 100},
        headers=headers,
    )

    # Transfer 40 from Store 1 to Store 2
    resp = client.post(
        "/api/v1/inventory/transfer",
        json={
            "product_id": p,
            "from_store_id": s1,
            "to_store_id": s2,
            "quantity": 40,
            "notes": "Replenishment transfer",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["quantity"] == 40
    assert data["previous_stock"] == 100
    assert data["new_stock"] == 60
    assert data["reference"] is not None
    assert data["reference"].startswith("TR-")

    # Verify inventory across stores
    inv_all = client.get("/api/v1/inventory", headers=headers).json()
    item_s1 = next(item for item in inv_all if item["store_id"] == s1 and item["product_id"] == p)
    assert item_s1["quantity"] == 60

    item_s2 = next(item for item in inv_all if item["store_id"] == s2 and item["product_id"] == p)
    assert item_s2["quantity"] == 40


def test_stock_transfer_rejects_same_store(auth_context):
    headers = auth_context["headers"]
    s1 = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/transfer",
        json={
            "product_id": p,
            "from_store_id": s1,
            "to_store_id": s1,
            "quantity": 10,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "from_store_id and to_store_id must be different" in resp.text


def test_stock_transfer_rejects_insufficient_stock(auth_context):
    headers = auth_context["headers"]
    s1 = auth_context["store1"]["id"]
    s2 = auth_context["store2"]["id"]
    p = auth_context["product"]["id"]

    # Stock in 15
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 15},
        headers=headers,
    )

    # Transfer 30
    resp = client.post(
        "/api/v1/inventory/transfer",
        json={
            "product_id": p,
            "from_store_id": s1,
            "to_store_id": s2,
            "quantity": 30,
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Insufficient stock in source store" in resp.text


# ==================== INVENTORY ADJUSTMENT TESTS ====================

def test_inventory_adjustment_increase_and_decrease(auth_context):
    headers = auth_context["headers"]
    s = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]

    # Increase 50
    r1 = client.post(
        "/api/v1/inventory/adjustment",
        json={
            "store_id": s,
            "product_id": p,
            "quantity": 50,
            "adjustment_type": "increase",
            "reason": "Physical stock count correction",
        },
        headers=headers,
    )
    assert r1.status_code == 201
    assert r1.json()["previous_stock"] == 0
    assert r1.json()["new_stock"] == 50
    assert r1.json()["reference"] is not None
    assert r1.json()["reference"].startswith("ADJ-")

    # Decrease 15
    r2 = client.post(
        "/api/v1/inventory/adjustment",
        json={
            "store_id": s,
            "product_id": p,
            "quantity": 15,
            "adjustment_type": "decrease",
            "reason": "Damaged stock adjustment",
        },
        headers=headers,
    )
    assert r2.status_code == 201
    assert r2.json()["previous_stock"] == 50
    assert r2.json()["new_stock"] == 35

    inv = client.get(f"/api/v1/inventory/{p}", headers=headers).json()
    assert inv["quantity"] == 35


@pytest.mark.parametrize("invalid_reason", ["", "   ", "string", "test", "----", "!@#$"])
def test_inventory_adjustment_rejects_invalid_reason(auth_context, invalid_reason):
    headers = auth_context["headers"]
    s = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]

    resp = client.post(
        "/api/v1/inventory/adjustment",
        json={
            "store_id": s,
            "product_id": p,
            "quantity": 10,
            "adjustment_type": "increase",
            "reason": invalid_reason,
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_inventory_adjustment_decrease_exceeding_stock(auth_context):
    headers = auth_context["headers"]
    s = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]

    # Stock in 10
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s, "product_id": p, "quantity": 10},
        headers=headers,
    )

    # Try decrease 20
    resp = client.post(
        "/api/v1/inventory/adjustment",
        json={
            "store_id": s,
            "product_id": p,
            "quantity": 20,
            "adjustment_type": "decrease",
            "reason": "Shrinkage write-off",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Insufficient stock for adjustment decrease" in resp.text


# ==================== EXPIRY API TESTS ====================

def test_expiry_inventory_endpoint(auth_context):
    headers = auth_context["headers"]
    # 1. No expired inventory case -> meaningful response
    resp = client.get("/api/v1/inventory/expiry", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data["success"] is True
    assert data["message"] == "No expired inventory found"
    assert data["data"] == []

    # 2. Expired inventory exists case
    s1 = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 10},
        headers=headers,
    )
    from unittest.mock import patch
    from app.models.inventory import Inventory
    with patch.object(Inventory, "expiry_date", new_callable=lambda: property(lambda self: date.today() - timedelta(days=10))):
        resp_exp = client.get("/api/v1/inventory/expiry", headers=headers)
        assert resp_exp.status_code == 200
        exp_data = resp_exp.json()
        assert isinstance(exp_data, list)
        assert len(exp_data) >= 1
        assert exp_data[0]["product_id"] == p


# ==================== DASHBOARD & VALUATION TESTS ====================

def test_inventory_dashboard_and_valuation(auth_context):
    headers = auth_context["headers"]
    s1 = auth_context["store1"]["id"]
    s2 = auth_context["store2"]["id"]
    p = auth_context["product"]["id"]

    # Stock in 50 in Store 1
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 50},
        headers=headers,
    )

    # Stock in 30 in Store 2
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s2, "product_id": p, "quantity": 30},
        headers=headers,
    )

    # Valuation
    val_resp = client.get("/api/v1/inventory/valuation", headers=headers)
    assert val_resp.status_code == 200
    # 80 items * 100.00 price = 8000.00
    expected_val = Decimal("80") * Decimal("100.00")
    assert Decimal(str(val_resp.json()["total_inventory_value"])) == expected_val

    # Dashboard
    dash_resp = client.get("/api/v1/inventory/dashboard", headers=headers)
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["total_products"] == 1  # 1 distinct product across 2 stores
    assert dash["total_stock"] == 80
    assert Decimal(str(dash["total_stock_value"])) == expected_val


def test_dashboard_and_valuation_empty_cases(auth_context):
    headers = auth_context["headers"]
    # Dashboard on empty tenant -> valid zero values
    dash_resp = client.get("/api/v1/inventory/dashboard", headers=headers)
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["total_products"] == 0
    assert dash["total_stock"] == 0
    assert Decimal(str(dash["total_stock_value"])) == Decimal("0.00")
    assert dash["low_stock_items"] == 0
    assert dash["expired_products"] == 0
    assert dash["pending_transfers"] == 0
    assert dash["pending_purchase_orders"] == 0

    # Valuation on empty tenant -> valid zero value
    val_resp = client.get("/api/v1/inventory/valuation", headers=headers)
    assert val_resp.status_code == 200
    val = val_resp.json()
    assert Decimal(str(val["total_inventory_value"])) == Decimal("0.00")


# ==================== GET ENDPOINT ERROR & EMPTY CHECKS ====================

def test_get_inventory_by_product_404_and_422(auth_context):
    headers = auth_context["headers"]
    p = auth_context["product"]["id"]

    # Nonexistent product -> 404
    r1 = client.get("/api/v1/inventory/999999", headers=headers)
    assert r1.status_code == 404
    assert "Product with ID 999999 not found" in r1.text

    # Product exists but has no inventory record -> 404
    p2 = client.post(
        "/api/v1/products",
        json={"name": "Widget No Inv", "sku": f"WGT-NOINV-{p}", "price": "50.00"},
        headers=headers,
    ).json()
    r_no_inv = client.get(f"/api/v1/inventory/{p2['id']}", headers=headers)
    assert r_no_inv.status_code == 404
    assert f"Inventory record for product with ID {p2['id']} not found" in r_no_inv.text

    # Invalid product ID <= 0 -> 422
    r2 = client.get("/api/v1/inventory/0", headers=headers)
    assert r2.status_code == 422
    r_neg = client.get("/api/v1/inventory/-5", headers=headers)
    assert r_neg.status_code == 422

    # Invalid product ID string/decimal -> 422
    r_str = client.get("/api/v1/inventory/invalid_id", headers=headers)
    assert r_str.status_code == 422
    r_dec = client.get("/api/v1/inventory/1.5", headers=headers)
    assert r_dec.status_code == 422


def test_list_inventory_empty_and_populated(auth_context):
    headers = auth_context["headers"]
    s1 = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]

    # 1. Before stock-in: empty inventory returns meaningful JSON response (not bare [])
    resp_empty = client.get("/api/v1/inventory", headers=headers)
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()
    assert isinstance(data_empty, dict)
    assert data_empty["success"] is True
    assert data_empty["message"] == "No inventory found"
    assert data_empty["data"] == []

    # 2. Stock in
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 25},
        headers=headers,
    )

    # 3. After stock-in: returns list of items directly
    resp = client.get("/api/v1/inventory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(item["product_id"] == p and item["quantity"] == 25 for item in data)


def test_movements_empty_and_populated(auth_context):
    headers = auth_context["headers"]
    s1 = auth_context["store1"]["id"]
    p = auth_context["product"]["id"]

    # 1. Before movements: returns meaningful response (not bare [])
    r_empty = client.get("/api/v1/inventory/movements", headers=headers)
    assert r_empty.status_code == 200
    data_empty = r_empty.json()
    assert isinstance(data_empty, dict)
    assert data_empty["success"] is True
    assert data_empty["message"] == "No inventory movements found"
    assert data_empty["data"] == []

    # 2. Invalid store_id -> 422
    r_inv = client.get("/api/v1/inventory/movements", params={"store_id": 0}, headers=headers)
    assert r_inv.status_code == 422
    r_neg = client.get("/api/v1/inventory/movements", params={"store_id": -1}, headers=headers)
    assert r_neg.status_code == 422

    # 3. Non-existent store_id -> 404
    r_nf = client.get("/api/v1/inventory/movements", params={"store_id": 999999}, headers=headers)
    assert r_nf.status_code == 404

    # 4. After movement: returns populated list
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 10},
        headers=headers,
    )
    r_pop = client.get("/api/v1/inventory/movements", headers=headers)
    assert r_pop.status_code == 200
    data_pop = r_pop.json()
    assert isinstance(data_pop, list)
    assert len(data_pop) >= 1


def test_low_stock_empty_and_validation(auth_context):
    headers = auth_context["headers"]

    # 1. No low-stock items -> meaningful no-data response
    r_empty = client.get("/api/v1/inventory/low-stock", headers=headers)
    assert r_empty.status_code == 200
    d_empty = r_empty.json()
    assert d_empty["success"] is True
    assert d_empty["message"] == "No low-stock items found"
    assert d_empty["count"] == 0
    assert d_empty["data"] == []

    # 2. Invalid store_id -> 422
    r_inv = client.get("/api/v1/inventory/low-stock", params={"store_id": 0}, headers=headers)
    assert r_inv.status_code == 422

    # 3. Non-existent store_id -> 404
    r_nf = client.get("/api/v1/inventory/low-stock", params={"store_id": 999999}, headers=headers)
    assert r_nf.status_code == 404


# ==================== TENANT ISOLATION TESTS ====================

def test_tenant_isolation(auth_context, unique_slug):
    headers_a = auth_context["headers"]
    s1_a = auth_context["store1"]["id"]
    p_a = auth_context["product"]["id"]

    # Stock in for Tenant A
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1_a, "product_id": p_a, "quantity": 50},
        headers=headers_a,
    )

    # Register Tenant B
    email_b = f"inv-b-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "TenantB",
            "slug": f"tb-{unique_slug[:6]}",
            "email": email_b,
            "admin_name": "Tenant B Admin",
            "password": "testpass123",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "testpass123"},
    ).json()
    headers_b = {"Authorization": f"Bearer {login_b['access_token']}"}

    # Tenant B tries to stock-out Tenant A's product -> 404
    resp = client.post(
        "/api/v1/inventory/stock-out",
        json={"store_id": s1_a, "product_id": p_a, "quantity": 10},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # Tenant B tries to access Tenant A's inventory -> 404
    r_get = client.get(f"/api/v1/inventory/{p_a}", headers=headers_b)
    assert r_get.status_code == 404


def test_all_7_get_apis_tenant_isolation(auth_context, unique_slug):
    headers_a = auth_context["headers"]
    s1_a = auth_context["store1"]["id"]
    p_a = auth_context["product"]["id"]

    # Stock in for Tenant A
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1_a, "product_id": p_a, "quantity": 50},
        headers=headers_a,
    )

    # Register Tenant B
    email_b = f"inv-iso-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "TenantIso",
            "slug": f"tiso-{unique_slug[:6]}",
            "email": email_b,
            "admin_name": "Tenant Iso Admin",
            "password": "testpass123",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "testpass123"},
    ).json()
    headers_b = {"Authorization": f"Bearer {login_b['access_token']}"}

    # 1. GET /inventory for Tenant B -> No inventory found
    r1 = client.get("/api/v1/inventory", headers=headers_b)
    assert r1.status_code == 200
    assert r1.json()["message"] == "No inventory found"
    assert r1.json()["data"] == []

    # 2. GET /inventory/{product_id} with Tenant A's product -> 404
    r2 = client.get(f"/api/v1/inventory/{p_a}", headers=headers_b)
    assert r2.status_code == 404

    # 3. GET /inventory/expiry for Tenant B -> No expired inventory found
    r3 = client.get("/api/v1/inventory/expiry", headers=headers_b)
    assert r3.status_code == 200
    assert r3.json()["message"] == "No expired inventory found"
    assert r3.json()["data"] == []

    # 4. GET /inventory/low-stock for Tenant B -> No low-stock items found
    r4 = client.get("/api/v1/inventory/low-stock", headers=headers_b)
    assert r4.status_code == 200
    assert r4.json()["message"] == "No low-stock items found"
    assert r4.json()["data"] == []

    # 5. GET /inventory/movements for Tenant B -> No inventory movements found
    r5 = client.get("/api/v1/inventory/movements", headers=headers_b)
    assert r5.status_code == 200
    assert r5.json()["message"] == "No inventory movements found"
    assert r5.json()["data"] == []

    # 6. GET /inventory/dashboard for Tenant B -> 0 values
    r6 = client.get("/api/v1/inventory/dashboard", headers=headers_b)
    assert r6.status_code == 200
    assert r6.json()["total_stock"] == 0
    assert Decimal(str(r6.json()["total_stock_value"])) == Decimal("0.00")

    # 7. GET /inventory/valuation for Tenant B -> 0.00
    r7 = client.get("/api/v1/inventory/valuation", headers=headers_b)
    assert r7.status_code == 200
    assert Decimal(str(r7.json()["total_inventory_value"])) == Decimal("0.00")
