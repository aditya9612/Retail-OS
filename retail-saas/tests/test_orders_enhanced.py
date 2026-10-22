from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.delivery import Delivery
from app.models.inventory import Inventory

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def setup_pos_env(unique_slug):
    email = f"pos-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "POS Enterprise Test",
            "slug": unique_slug,
            "email": email,
            "admin_name": "POS Admin",
            "password": "testpass123",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": "SuperStore Pune", "code": f"SP-{unique_slug[:4]}"},
        headers=headers,
    ).json()

    # Product 1 with variants
    p1 = client.post(
        "/api/v1/products",
        json={"name": "Polo T-Shirt", "sku": f"TSHIRT-{unique_slug[:4]}", "price": "500.00"},
        headers=headers,
    ).json()

    v1 = client.post(
        f"/api/v1/products/{p1['id']}/variants",
        json={"variant_name": "Red M", "sku": f"RED-M-{unique_slug[:4]}", "selling_price": "500.00"},
        headers=headers,
    ).json()

    v2 = client.post(
        f"/api/v1/products/{p1['id']}/variants",
        json={"variant_name": "Blue L", "sku": f"BLU-L-{unique_slug[:4]}", "selling_price": "550.00"},
        headers=headers,
    ).json()

    # Product 2 standard
    p2 = client.post(
        "/api/v1/products",
        json={"name": "Denim Jeans", "sku": f"JEANS-{unique_slug[:4]}", "price": "1200.00"},
        headers=headers,
    ).json()

    # Stock in
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": p1["id"], "quantity": 100},
        headers=headers,
    )
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": p2["id"], "quantity": 50},
        headers=headers,
    )

    return headers, store, p1, v1, v2, p2


def test_variant_duplicate_validation(setup_pos_env):
    """Verify duplicate validation allows different variants of same product, but blocks identical items."""
    headers, store, p1, v1, v2, _ = setup_pos_env

    # 1. Same product, same variant -> should fail
    resp_dup = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [
                {"product_id": p1["id"], "variant_id": v1["id"], "quantity": 1},
                {"product_id": p1["id"], "variant_id": v1["id"], "quantity": 2},
            ],
        },
        headers=headers,
    )
    assert resp_dup.status_code == 422
    assert "duplicate products" in resp_dup.text.lower()

    # 2. Same product, distinct variants -> should succeed!
    resp_valid = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [
                {"product_id": p1["id"], "variant_id": v1["id"], "quantity": 1},
                {"product_id": p1["id"], "variant_id": v2["id"], "quantity": 2},
            ],
        },
        headers=headers,
    )
    assert resp_valid.status_code == 201
    data = resp_valid.json()
    assert len(data["items"]) == 2


def test_pos_order_no_delivery_creation(setup_pos_env, db):
    """Over-the-counter POS order should not create an unneeded Delivery record, while ecommerce orders do."""
    headers, store, p1, _, _, p2 = setup_pos_env

    # 1. POS order (walk-in)
    pos_order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "pos",
            "items": [{"product_id": p2["id"], "quantity": 1}],
        },
        headers=headers,
    ).json()

    confirm_resp = client.post(f"/api/v1/orders/{pos_order['id']}/confirm", headers=headers)
    assert confirm_resp.status_code == 200

    # Verify no delivery record
    pos_delivery = db.query(Delivery).filter(Delivery.order_id == pos_order["id"]).first()
    assert pos_delivery is None

    # 2. Ecommerce order with delivery address
    ecom_order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "ecommerce",
            "delivery_address": "Flat 402, MG Road, Pune",
            "items": [{"product_id": p2["id"], "quantity": 1}],
        },
        headers=headers,
    ).json()

    confirm_ecom = client.post(f"/api/v1/orders/{ecom_order['id']}/confirm", headers=headers)
    assert confirm_ecom.status_code == 200

    ecom_delivery = db.query(Delivery).filter(Delivery.order_id == ecom_order["id"]).first()
    assert ecom_delivery is not None
    assert ecom_delivery.status == "pending"


def test_order_cancellation_stock_restoration(setup_pos_env, db):
    """Cancelling a confirmed order with restore_stock=True restores deducted inventory."""
    headers, store, _, _, _, p2 = setup_pos_env

    # Check initial stock
    inv_before = db.query(Inventory).filter(
        Inventory.store_id == store["id"],
        Inventory.product_id == p2["id"]
    ).first()
    initial_qty = inv_before.quantity

    # Create and confirm order (takes 5 units)
    order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [{"product_id": p2["id"], "quantity": 5}],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/orders/{order['id']}/confirm", headers=headers)

    db.refresh(inv_before)
    assert inv_before.quantity == initial_qty - 5

    # Cancel with restore_stock=True
    cancel_resp = client.post(
        f"/api/v1/orders/{order['id']}/cancel?restore_stock=true",
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    db.refresh(inv_before)
    assert inv_before.quantity == initial_qty


def test_draft_order_add_items(setup_pos_env):
    """Adding line items to a draft order via POST /{order_id}/items."""
    headers, store, p1, _, _, p2 = setup_pos_env

    # Create draft with 1 item
    order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [{"product_id": p1["id"], "quantity": 2}],
        },
        headers=headers,
    ).json()
    assert len(order["items"]) == 1

    # Add second item
    add_resp = client.post(
        f"/api/v1/orders/{order['id']}/items",
        json={
            "items": [{"product_id": p2["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert add_resp.status_code == 200
    updated = add_resp.json()
    assert len(updated["items"]) == 2
    assert float(updated["total_amount"]) > float(order["total_amount"])


def test_pos_checkout_atomic_flow(setup_pos_env):
    """POST /api/v1/orders/pos-checkout executes order + stock out + payment + invoice atomically."""
    headers, store, _, _, _, p2 = setup_pos_env

    checkout_payload = {
        "store_id": store["id"],
        "items": [{"product_id": p2["id"], "quantity": 2}],
        "payment": {
            "payment_method": "cash",
            "amount": "3000.00",
            "notes": "Customer paid with 3x1000 notes",
        },
        "generate_invoice": True,
    }

    resp = client.post("/api/v1/orders/pos-checkout", json=checkout_payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    # Order checks
    order = data["order"]
    assert order["status"] == "confirmed"
    assert order["payment_status"] == "paid"
    assert order["order_type"] == "pos"

    # Payment checks
    payment = data["payment"]
    assert payment is not None
    assert payment["status"] == "completed"
    assert payment["payment_method"] == "cash"
    assert float(payment["amount"]) == float(order["total_amount"])

    # Change due check
    expected_change = Decimal("3000.00") - Decimal(str(order["total_amount"]))
    assert Decimal(str(data["change_due"])) == expected_change

    # Invoice checks
    invoice = data["invoice"]
    assert invoice is not None
    assert invoice["status"] == "issued"
    assert invoice["order_id"] == order["id"]


def test_orders_stats_endpoint(setup_pos_env):
    """GET /api/v1/orders/stats returns real-time dashboard KPIs."""
    headers, store, _, _, _, _ = setup_pos_env

    resp = client.get(f"/api/v1/orders/stats?store_id={store['id']}", headers=headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert "total_orders" in stats
    assert "total_revenue" in stats
    assert "draft_orders" in stats
    assert "confirmed_orders" in stats
    assert "cancelled_orders" in stats
    assert "average_order_value" in stats


def test_order_receipt_endpoint(setup_pos_env):
    """GET /api/v1/orders/{order_id}/receipt returns structured details and formatted ASCII receipt."""
    headers, store, _, _, _, p2 = setup_pos_env

    order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [{"product_id": p2["id"], "quantity": 1}],
        },
        headers=headers,
    ).json()

    receipt_resp = client.get(f"/api/v1/orders/{order['id']}/receipt", headers=headers)
    assert receipt_resp.status_code == 200
    receipt = receipt_resp.json()

    assert receipt["order_id"] == order["id"]
    assert receipt["store_name"] == store["name"]
    assert len(receipt["items"]) == 1
    assert "formatted_receipt" in receipt
    assert "TOTAL AMOUNT" in receipt["formatted_receipt"]
    assert store["name"] in receipt["formatted_receipt"]


def test_orders_export_endpoint(setup_pos_env):
    """GET /api/v1/orders/export provides streaming Excel and CSV downloads."""
    headers, store, _, _, _, _ = setup_pos_env

    # 1. Excel export
    excel_resp = client.get("/api/v1/orders/export?format=excel", headers=headers)
    assert excel_resp.status_code == 200
    assert "application/vnd.openxmlformats" in excel_resp.headers["content-type"]
    assert "orders.xlsx" in excel_resp.headers["content-disposition"]
    assert len(excel_resp.content) > 0

    # 2. CSV export
    csv_resp = client.get("/api/v1/orders/export?format=csv", headers=headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "orders.csv" in csv_resp.headers["content-disposition"]
    assert b"Order Number" in csv_resp.content


def test_list_orders_filtering_and_search(setup_pos_env):
    """GET /api/v1/orders with search and status query parameters."""
    headers, store, _, _, _, p2 = setup_pos_env

    order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [{"product_id": p2["id"], "quantity": 1}],
            "notes": "Urgent gift packing needed",
        },
        headers=headers,
    ).json()

    # Search by note keyword
    search_resp = client.get("/api/v1/orders?search=gift", headers=headers)
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert any(o["id"] == order["id"] for o in results)

    # Filter by draft status
    status_resp = client.get("/api/v1/orders?status=draft", headers=headers)
    assert status_resp.status_code == 200
    assert all(o["status"] == "draft" for o in status_resp.json())

