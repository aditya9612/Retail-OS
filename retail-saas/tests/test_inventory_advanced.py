from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def inv_advanced_context(unique_slug):
    email = f"adv-inv-{unique_slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "AdvInventoryTest",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Adv Admin",
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
        json={"name": "Downtown Outlet", "code": f"DT-{unique_slug[:4]}"},
        headers=headers,
    ).json()

    # Create Store 2
    store2 = client.post(
        "/api/v1/stores",
        json={"name": "Uptown Outlet", "code": f"UT-{unique_slug[:4]}"},
        headers=headers,
    ).json()

    # Create Category
    cat_resp = client.post(
        "/api/v1/categories",
        json={"name": f"Dairy & Frozen {unique_slug[:4]}", "description": "Fresh and frozen dairy products"},
        headers=headers,
    )
    assert cat_resp.status_code == 201
    category = cat_resp.json()

    # Create Product 1
    prod1 = client.post(
        "/api/v1/products",
        json={
            "name": f"Organic Whole Milk {unique_slug[:4]}",
            "sku": f"MILK-{unique_slug[:6]}",
            "price": 60.00,
            "cost_price": 45.00,
            "category_id": category["id"],
        },
        headers=headers,
    ).json()

    # Create Product 2
    prod2 = client.post(
        "/api/v1/products",
        json={
            "name": f"Greek Yogurt {unique_slug[:4]}",
            "sku": f"YGRT-{unique_slug[:6]}",
            "price": 120.00,
            "cost_price": 80.00,
            "category_id": category["id"],
        },
        headers=headers,
    ).json()

    return {
        "headers": headers,
        "store1": store1,
        "store2": store2,
        "category": category,
        "product1": prod1,
        "product2": prod2,
    }


def test_near_expiry_api(inv_advanced_context):
    headers = inv_advanced_context["headers"]
    s1 = inv_advanced_context["store1"]["id"]
    p1 = inv_advanced_context["product1"]["id"]

    today = date.today()
    exp_15_days = (today + timedelta(days=15)).isoformat()

    # Stock in item expiring in 15 days
    client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": s1,
            "product_id": p1,
            "quantity": 30,
            "batch_number": "BATCH-EXP-15",
            "expiry_date": exp_15_days,
            "unit_cost": "45.00",
            "notes": "Near expiry test batch",
        },
        headers=headers,
    )

    # 1. Check with days=30 (should include our product)
    resp_30 = client.get("/api/v1/inventory/near-expiry?days=30", headers=headers)
    assert resp_30.status_code == 200
    body_30 = resp_30.json()
    assert body_30["success"] is True
    assert body_30["count"] >= 1
    matching = [item for item in body_30["data"] if item["product_id"] == p1]
    assert len(matching) == 1
    assert matching[0]["days_until_expiry"] == 15
    assert matching[0]["quantity"] == 30
    assert matching[0]["product_name"] == inv_advanced_context["product1"]["name"]

    # 2. Check with days=10 (should NOT include our product expiring in 15 days)
    resp_10 = client.get("/api/v1/inventory/near-expiry?days=10", headers=headers)
    assert resp_10.status_code == 200
    body_10 = resp_10.json()
    assert not any(item["product_id"] == p1 for item in body_10["data"])


def test_product_multi_store_availability_api(inv_advanced_context):
    headers = inv_advanced_context["headers"]
    s1 = inv_advanced_context["store1"]["id"]
    s2 = inv_advanced_context["store2"]["id"]
    p = inv_advanced_context["product1"]["id"]

    # Stock in Store 1: 50 units
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p, "quantity": 50, "unit_cost": "45.00"},
        headers=headers,
    )

    # Stock in Store 2: 75 units
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s2, "product_id": p, "quantity": 75, "unit_cost": "45.00"},
        headers=headers,
    )

    # Call multi-store API
    resp = client.get(f"/api/v1/inventory/product/{p}/stores", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["product_id"] == p
    assert data["total_stock"] == 125
    assert data["stores_count"] >= 2

    positions = {item["store_id"]: item["quantity"] for item in data["data"]}
    assert positions[s1] == 50
    assert positions[s2] == 75


def test_inventory_valuation_breakdown_api(inv_advanced_context):
    headers = inv_advanced_context["headers"]
    s1 = inv_advanced_context["store1"]["id"]
    p1 = inv_advanced_context["product1"]["id"]
    p2 = inv_advanced_context["product2"]["id"]

    # Stock in 100 units of Product 1 (cost 45, price 60)
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p1, "quantity": 100, "unit_cost": "45.00"},
        headers=headers,
    )

    # Stock in 50 units of Product 2 (cost 80, price 120)
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p2, "quantity": 50, "unit_cost": "80.00"},
        headers=headers,
    )

    # Call valuation breakdown API
    resp = client.get("/api/v1/inventory/valuation/breakdown", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    summary = data["summary"]
    # Total cost = 100*45 + 50*80 = 4500 + 4000 = 8500
    # Total retail = 100*60 + 50*120 = 6000 + 6000 = 12000
    assert Decimal(str(summary["total_cost_value"])) == Decimal("8500.00")
    assert Decimal(str(summary["total_retail_value"])) == Decimal("12000.00")
    assert Decimal(str(summary["potential_gross_profit"])) == Decimal("3500.00")
    assert summary["potential_margin_percentage"] > 0

    assert len(data["stores_breakdown"]) >= 1
    assert len(data["categories_breakdown"]) >= 1


def test_bulk_adjust_inventory_api(inv_advanced_context):
    headers = inv_advanced_context["headers"]
    s1 = inv_advanced_context["store1"]["id"]
    p1 = inv_advanced_context["product1"]["id"]
    p2 = inv_advanced_context["product2"]["id"]

    # Initial stock: Product 1 has 40, Product 2 has 20
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p1, "quantity": 40, "unit_cost": "45.00"},
        headers=headers,
    )
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p2, "quantity": 20, "unit_cost": "80.00"},
        headers=headers,
    )

    # Physical stock count audit:
    # Product 1 counted = 45 (diff +5)
    # Product 2 counted = 15 (diff -5)
    audit_payload = {
        "store_id": s1,
        "audit_reference": "AUDIT-2026-Q4",
        "items": [
            {"product_id": p1, "counted_quantity": 45, "reason": "Found extra unopened carton"},
            {"product_id": p2, "counted_quantity": 15, "reason": "Damaged goods discarded"},
        ],
    }

    adj_resp = client.post("/api/v1/inventory/bulk-adjust", json=audit_payload, headers=headers)
    assert adj_resp.status_code == 201, adj_resp.text
    adj_data = adj_resp.json()
    assert adj_data["success"] is True
    assert adj_data["total_items_processed"] == 2
    assert adj_data["adjusted_items_count"] == 2
    assert adj_data["audit_reference"] == "AUDIT-2026-Q4"

    # Verify inventory is updated
    inv1 = client.get(f"/api/v1/inventory/{p1}?store_id={s1}", headers=headers).json()
    assert inv1["quantity"] == 45

    inv2 = client.get(f"/api/v1/inventory/{p2}?store_id={s1}", headers=headers).json()
    assert inv2["quantity"] == 15


def test_enhanced_list_and_filters(inv_advanced_context):
    headers = inv_advanced_context["headers"]
    s1 = inv_advanced_context["store1"]["id"]
    s2 = inv_advanced_context["store2"]["id"]
    p1 = inv_advanced_context["product1"]["id"]

    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": s1, "product_id": p1, "quantity": 80, "unit_cost": "45.00"},
        headers=headers,
    )

    # 1. Filter by store_id
    resp_s1 = client.get(f"/api/v1/inventory?store_id={s1}", headers=headers)
    assert resp_s1.status_code == 200
    items_s1 = resp_s1.json()
    assert isinstance(items_s1, list)
    assert all(item["store_id"] == s1 for item in items_s1)

    # 2. Enriched fields in InventoryResponse
    item = next(i for i in items_s1 if i["product_id"] == p1)
    assert item["product_name"] == inv_advanced_context["product1"]["name"]
    assert item["product_sku"] == inv_advanced_context["product1"]["sku"]
    assert item["store_name"] == inv_advanced_context["store1"]["name"]

    # 3. Filter by search
    resp_search = client.get("/api/v1/inventory?search=Whole+Milk", headers=headers)
    assert resp_search.status_code == 200
    search_items = resp_search.json()
    assert len(search_items) >= 1

