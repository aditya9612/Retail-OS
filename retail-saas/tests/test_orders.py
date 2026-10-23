import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def setup_order_flow(unique_slug):
    email = f"order-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Order Test",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Order Admin",
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
        json={"name": "Test Store", "code": "TS1"},
        headers=headers,
    ).json()

    product = client.post(
        "/api/v1/products",
        json={"name": "Order Product", "sku": "ORD-001", "price": "100.00", "tax_rate": 18.0},
        headers=headers,
    ).json()

    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product["id"], "quantity": 50},
        headers=headers,
    )

    return headers, store, product


def test_create_and_confirm_order(setup_order_flow):
    headers, store, product = setup_order_flow

    order_resp = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
        headers=headers,
    )
    assert order_resp.status_code == 201
    order = order_resp.json()
    assert order["status"] == "draft"

    confirm_resp = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"


def test_order_creation_pincode_extraction_and_item_totals(setup_order_flow):
    headers, store, product = setup_order_flow

    # 1. Pincode extracted from delivery_address & item total calculation
    order_resp = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "delivery_address": "Flat 204, Green Park, Baner, Pune, Maharashtra, 411045",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 2,
                    "unit_price": 250.0,
                    "discount": 10.0,
                }
            ],
        },
        headers=headers,
    )
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()

    # Verify Issue 4: delivery_pincode is extracted
    assert order["delivery_pincode"] == "411045"

    # Verify Issue 2: Order Item Total Matches Quantity * Unit Price - Discount
    item = order["items"][0]
    assert item["quantity"] == 2
    assert float(item["unit_price"]) == 250.0
    assert float(item["discount"]) == 10.0
    assert float(item["total"]) == 490.00  # (2 * 250.0) - 10.0 = 490.00
    assert float(item["tax_amount"]) == 88.20  # 18% of 490 = 88.20
    assert float(item["total_amount"]) == 578.20

    # Verify Issue 1: Order Total Amount Matches Item Total
    assert order["total_amount"] == item["total_amount"]
    assert float(order["subtotal"]) == 490.00
    assert float(order["total_amount"]) == 578.20


def test_draft_order_coupon_discount_applied_only_on_confirm(setup_order_flow):
    headers, store, product = setup_order_flow
    from datetime import date, timedelta

    # Create coupon WELCOME10 (10% discount)
    today = date.today()
    future = today + timedelta(days=30)
    cpn_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "WELCOME10",
            "description": "Welcome discount",
            "discount_type": "percentage",
            "discount_value": 10.0,
            "minimum_order_amount": 50.0,
            "maximum_discount": 100.0,
            "usage_limit": 100,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=headers,
    )
    assert cpn_resp.status_code == 201, cpn_resp.text

    # Create draft order with coupon WELCOME10
    order_resp = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "pos",
            "coupon_code": "WELCOME10",
            "delivery_address": "Flat 204, Green Park, Baner, Pune, Maharashtra, 411045",
            "notes": "Deliver before 6 PM",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 2,
                    "unit_price": 250.0,
                    "discount": 10.0,
                }
            ],
        },
        headers=headers,
    )
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()

    # Verify Issue 3: Draft order does NOT have coupon discount applied
    assert order["status"] == "draft"
    assert order["coupon_code"] == "WELCOME10"
    assert float(order["discount_amount"]) == 0.00
    assert float(order["subtotal"]) == 490.00
    assert float(order["tax_amount"]) == 88.20
    assert float(order["total_amount"]) == 578.20

    # Verify Issue 1: Order Total Amount Matches Item Total
    assert order["total_amount"] == order["items"][0]["total_amount"]

    # Verify Issue 2: Order Item Total Matches Quantity & Unit Price
    assert float(order["items"][0]["total"]) == 490.00

    # Verify Issue 4: delivery_pincode is extracted
    assert order["delivery_pincode"] == "411045"

    # Verify coupon used_count has NOT incremented while in draft
    coupon_id = cpn_resp.json()["id"]
    cpn_check = client.get(f"/api/v1/coupons/{coupon_id}", headers=headers).json()
    assert cpn_check["used_count"] == 0

    # Confirm order -> NOW coupon discount is applied and used_count increments
    confirm_resp = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    confirmed = confirm_resp.json()

    assert confirmed["status"] == "confirmed"
    assert float(confirmed["discount_amount"]) == 49.00  # 10% of 490
    assert float(confirmed["total_amount"]) == 529.20  # 578.20 - 49.00 = 529.20

    # Coupon used_count incremented to 1
    cpn_check_after = client.get(f"/api/v1/coupons/{coupon_id}", headers=headers).json()
    assert cpn_check_after["used_count"] == 1

