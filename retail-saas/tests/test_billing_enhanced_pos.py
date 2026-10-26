import random
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def pos_setup(unique_slug):
    email = f"pos-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "POS Billing Store",
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
        json={"name": "POS Branch 1", "code": f"PB_{unique_slug[:4]}"},
        headers=headers,
    ).json()

    rand_digits1 = str(random.randint(100000, 999999))
    rand_digits2 = str(random.randint(100000, 999999))
    barcode1 = f"8901234{rand_digits1}"
    barcode2 = f"8909876{rand_digits2}"

    # Product 1 with barcode
    p1_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Barcode Tea 500g",
            "sku": f"TEA-{unique_slug[:4]}",
            "barcode": barcode1,
            "price": "150.00",
            "gst_rate": "5.00",
            "hsn_code": "0902",
        },
        headers=headers,
    )
    assert p1_resp.status_code == 201, p1_resp.text
    product1 = p1_resp.json()

    # Product 2 with SKU
    p2_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Biscuits 200g",
            "sku": f"BISC-{unique_slug[:4]}",
            "barcode": barcode2,
            "price": "50.00",
            "gst_rate": "18.00",
            "hsn_code": "1905",
        },
        headers=headers,
    )
    assert p2_resp.status_code == 201, p2_resp.text
    product2 = p2_resp.json()

    # Stock in
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product1["id"], "quantity": 50},
        headers=headers,
    )
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product2["id"], "quantity": 20},
        headers=headers,
    )

    rand_phone = f"98234{random.randint(10000, 99999)}"
    # Customer
    customer = client.post(
        "/api/v1/customers",
        json={
            "name": "Loyal Customer",
            "phone": rand_phone,
            "email": f"cust-{unique_slug}@test.com",
        },
        headers=headers,
    ).json()

    return headers, store, product1, product2, customer


def test_barcode_scan_and_auto_increment(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    # 1. Clear cart
    client.delete("/api/v1/billing/cart/clear", headers=headers)

    # 2. Scan barcode first time
    scan_resp = client.post(
        "/api/v1/billing/cart/scan",
        json={
            "barcode": product1["barcode"],
            "store_id": store["id"],
            "quantity": 1,
        },
        headers=headers,
    )
    assert scan_resp.status_code == 200, scan_resp.text
    cart = scan_resp.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["product_id"] == product1["id"]
    assert Decimal(cart["items"][0]["quantity"]) == Decimal("1")

    # 3. Scan barcode second time (should increment quantity to 2)
    scan_resp2 = client.post(
        "/api/v1/billing/cart/scan",
        json={
            "barcode": product1["barcode"],
            "store_id": store["id"],
            "quantity": 1,
        },
        headers=headers,
    )
    assert scan_resp2.status_code == 200
    cart2 = scan_resp2.json()
    assert len(cart2["items"]) == 1
    assert Decimal(cart2["items"][0]["quantity"]) == Decimal("2")


def test_sku_scan_success(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    client.delete("/api/v1/billing/cart/clear", headers=headers)

    # Scan by SKU
    scan_resp = client.post(
        "/api/v1/billing/cart/scan",
        json={
            "barcode": product2["sku"],
            "store_id": store["id"],
            "quantity": 2,
        },
        headers=headers,
    )
    assert scan_resp.status_code == 200
    cart = scan_resp.json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["product_id"] == product2["id"]
    assert Decimal(cart["items"][0]["quantity"]) == Decimal("2")


def test_barcode_scan_not_found(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    scan_resp = client.post(
        "/api/v1/billing/cart/scan",
        json={
            "barcode": "9999999999999",
            "store_id": store["id"],
        },
        headers=headers,
    )
    assert scan_resp.status_code == 404
    assert "not found" in str(scan_resp.json()).lower()


def test_cart_clear_endpoint(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    # Add item
    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product1["id"], "quantity": "1"},
        headers=headers,
    )

    get_resp = client.get("/api/v1/billing/cart", headers=headers)
    assert len(get_resp.json()["items"]) >= 1

    # Clear cart
    clear_resp = client.delete("/api/v1/billing/cart/clear", headers=headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json()["items"] == []
    assert clear_resp.json()["grand_total"] == "0.00"


def test_update_item_zero_quantity_removes(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    client.delete("/api/v1/billing/cart/clear", headers=headers)

    # Add item
    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product1["id"], "quantity": "3"},
        headers=headers,
    )

    # Update item to quantity 0
    update_resp = client.put(
        "/api/v1/billing/cart/update-item",
        json={"product_id": product1["id"], "quantity": "0"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert len(update_resp.json()["items"]) == 0


def test_cart_customer_association_and_removal(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    client.delete("/api/v1/billing/cart/clear", headers=headers)

    # 1. Attach customer by ID
    cust_resp = client.post(
        "/api/v1/billing/cart/customer",
        json={"customer_id": customer["id"]},
        headers=headers,
    )
    assert cust_resp.status_code == 200
    data = cust_resp.json()
    assert data["customer_id"] == customer["id"]
    assert data["name"] == customer["name"]
    assert data["phone"] == customer["phone"]

    # Verify cart has customer_id
    cart_resp = client.get("/api/v1/billing/cart", headers=headers)
    assert cart_resp.json()["customer_id"] == customer["id"]

    # 2. Attach customer by Phone
    cust_phone_resp = client.post(
        "/api/v1/billing/cart/customer",
        json={"phone": customer["phone"]},
        headers=headers,
    )
    assert cust_phone_resp.status_code == 200
    assert cust_phone_resp.json()["customer_id"] == customer["id"]

    # 3. Detach customer
    detach_resp = client.delete("/api/v1/billing/cart/customer", headers=headers)
    assert detach_resp.status_code == 200
    assert detach_resp.json()["customer_id"] is None


def test_validate_stock_endpoint(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    client.delete("/api/v1/billing/cart/clear", headers=headers)

    # Add 5 of product1 (stock is 50 -> sufficient)
    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product1["id"], "quantity": "5"},
        headers=headers,
    )

    val_resp = client.get(
        "/api/v1/billing/cart/validate-stock",
        params={"store_id": store["id"]},
        headers=headers,
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["is_valid"] is True
    assert val_data["insufficient_items_count"] == 0
    assert len(val_data["items"]) == 1
    assert val_data["items"][0]["is_sufficient"] is True


def test_direct_billing_checkout_endpoint(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    client.delete("/api/v1/billing/cart/clear", headers=headers)

    # Add items to cart
    add_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product1["id"], "quantity": "2"},
        headers=headers,
    )
    grand_total = add_resp.json()["grand_total"]

    # Checkout directly via POST /api/v1/billing/checkout
    checkout_resp = client.post(
        "/api/v1/billing/checkout",
        json={
            "store_id": store["id"],
            "customer_id": customer["id"],
            "payments": [
                {"payment_mode": "cash", "amount": grand_total},
            ],
        },
        headers=headers,
    )
    assert checkout_resp.status_code == 201, checkout_resp.text
    invoice = checkout_resp.json()
    assert invoice["invoice_number"].startswith("INV-")
    assert invoice["total_amount"] == grand_total

    # Verify active cart was cleared automatically upon successful checkout
    cart_after = client.get("/api/v1/billing/cart", headers=headers).json()
    assert len(cart_after["items"]) == 0


def test_tender_change_with_split_and_denominations(pos_setup):
    headers, store, product1, product2, customer = pos_setup

    # Payable: 1250.00
    # Other payments: UPI 500.00
    # Net cash payable: 750.00
    # Tendered cash: 1000.00
    # Change due: 250.00 (500: 0, 200: 1, 100: 0, 50: 1)
    res = client.post(
        "/api/v1/billing/tender-change/calculate",
        json={
            "payable_amount": "1250.00",
            "tendered_amount": "1000.00",
            "other_payments": [
                {"mode": "upi", "amount": "500.00"},
            ],
            "calculate_denominations": True,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["other_payments_total"] == "500.00"
    assert data["net_payable_cash"] == "750.00"
    assert data["change_due"] == "250.00"
    assert data["is_exact"] is False
    assert data["denominations"] is not None
    assert data["denominations"].get("200") == 1
    assert data["denominations"].get("50") == 1

