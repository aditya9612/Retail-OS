from decimal import Decimal
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order
from app.models.product import Product
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


@pytest.fixture(scope="module")
def storefront_test_context():
    db = SessionLocal()
    try:
        # 1. Ensure Tenant 1 exists
        tenant = db.query(Tenant).filter(Tenant.id == 1).first()
        if not tenant:
            tenant = Tenant(
                id=1,
                name="Storefront Test Tenant",
                domain="storefront.test",
                is_active=True,
            )
            db.add(tenant)
            db.flush()

        # 2. Ensure Store exists
        store = db.query(Store).filter(Store.tenant_id == 1).first()
        if not store:
            store = Store(
                tenant_id=1,
                name="Central Mart",
                code="CM-01",
                is_main=True,
                is_active=True,
            )
            db.add(store)
            db.flush()

        # 3. Create sample Category
        cat = db.query(Category).filter(Category.tenant_id == 1).first()
        if not cat:
            cat = Category(
                tenant_id=1,
                name="Groceries",
                description="Daily essential groceries",
                is_active=True,
            )
            db.add(cat)
            db.flush()

        # 4. Create sample Products
        prod1 = db.query(Product).filter(Product.tenant_id == 1, Product.sku == "GROC-SUG-01").first()
        if not prod1:
            prod1 = Product(
                tenant_id=1,
                category_id=cat.id,
                name="Madhur Sugar 1kg",
                sku="GROC-SUG-01",
                selling_price=Decimal("45.00"),
                mrp=Decimal("50.00"),
                unit="kg",
                is_active=True,
            )
            db.add(prod1)

        prod2 = db.query(Product).filter(Product.tenant_id == 1, Product.sku == "GROC-OIL-01").first()
        if not prod2:
            prod2 = Product(
                tenant_id=1,
                category_id=cat.id,
                name="Fortune Sunflower Oil 1L",
                sku="GROC-OIL-01",
                selling_price=Decimal("135.00"),
                mrp=Decimal("150.00"),
                unit="ltr",
                is_active=True,
            )
            db.add(prod2)

        # 5. Create Test Customer (Rahul Sharma)
        customer_phone = "9822145672"
        cust = db.query(Customer).filter(Customer.phone == customer_phone).first()
        if not cust:
            cust = Customer(
                tenant_id=1,
                name="Rahul Ramesh Sharma",
                phone=customer_phone,
                email="rahul.sharma@example.com",
                address="Flat 402, Green Park Residency, Pune",
                loyalty_points=150,
                status="active",
                is_mobile_verified=True,
            )
            db.add(cust)
            db.flush()
        else:
            cust.status = "active"

        db.commit()
        db.refresh(cust)

        return {
            "customer_phone": customer_phone,
            "customer_id": cust.id,
            "product_id": prod1.id if prod1 else 1,
            "product2_id": prod2.id if prod2 else 2,
        }
    finally:
        db.close()


@pytest.fixture
def customer_auth_headers(storefront_test_context, monkeypatch):
    phone = storefront_test_context["customer_phone"]
    monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
    client.post(
        "/api/v1/auth/login/mobile-otp/request",
        json={"phone": phone},
    )
    resp = client.post(
        "/api/v1/auth/login/mobile-otp/verify",
        json={"phone": phone, "otp": "123456"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------------------
# 1. Unified Mobile OTP Login for Customer
# ------------------------------------------------------------------------------

def test_customer_mobile_otp_login(storefront_test_context, monkeypatch):
    phone = storefront_test_context["customer_phone"]
    monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)

    # 1. Request OTP via existing unified endpoint
    req_resp = client.post(
        "/api/v1/auth/login/mobile-otp/request",
        json={"phone": phone},
    )
    assert req_resp.status_code == 200
    assert req_resp.json()["success"] is True

    # 2. Verify OTP via existing unified endpoint (mocked to 123456)
    verify_resp = client.post(
        "/api/v1/auth/login/mobile-otp/verify",
        json={"phone": phone, "otp": "123456"},
    )
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify decoded token payload has role='customer'
    from app.core.security import decode_token
    payload = decode_token(data["access_token"])
    assert payload["role"] == "customer"
    assert payload["phone"] == phone


# ------------------------------------------------------------------------------
# 2. Storefront Catalog & Product Browsing
# ------------------------------------------------------------------------------

def test_storefront_catalog_browsing(customer_auth_headers):
    # 1. Categories
    cat_resp = client.get("/api/v1/storefront/categories", headers=customer_auth_headers)
    assert cat_resp.status_code == 200
    cat_body = cat_resp.json()
    assert isinstance(cat_body["items"], list)
    assert cat_body["counts"]["total"] == cat_body["total"]

    # 2. Products List
    prod_resp = client.get("/api/v1/storefront/products", headers=customer_auth_headers)
    assert prod_resp.status_code == 200
    pdata = prod_resp.json()
    assert "items" in pdata
    assert "total" in pdata
    assert "counts" in pdata
    assert pdata["counts"]["total"] == pdata["total"]
    assert pdata["total"] >= 1

    # 3. Product Search
    search_resp = client.get("/api/v1/storefront/products?search=Sugar", headers=customer_auth_headers)
    assert search_resp.status_code == 200
    s_items = search_resp.json()["items"]
    assert any("Sugar" in p["name"] for p in s_items)


# ------------------------------------------------------------------------------
# 3. Customer Cart Lifecycle (Add, Update, Remove, View)
# ------------------------------------------------------------------------------

def test_storefront_cart_lifecycle(storefront_test_context, customer_auth_headers):
    pid = storefront_test_context["product_id"]
    pid2 = storefront_test_context["product2_id"]

    # 1. Clear cart
    client.delete("/api/v1/storefront/cart", headers=customer_auth_headers)

    # 2. Get Cart (empty)
    cart_resp = client.get("/api/v1/storefront/cart", headers=customer_auth_headers)
    assert cart_resp.status_code == 200
    assert cart_resp.json()["total_items"] == 0

    # 3. Add Item 1 (Quantity 2)
    add_resp = client.post(
        "/api/v1/storefront/cart/items",
        json={"product_id": pid, "quantity": 2},
        headers=customer_auth_headers,
    )
    assert add_resp.status_code == 200
    cart_data = add_resp.json()
    assert cart_data["total_items"] == 2
    assert float(cart_data["subtotal"]) == 90.00  # 45.00 * 2

    # 4. Add Item 2 (Quantity 1)
    add2_resp = client.post(
        "/api/v1/storefront/cart/items",
        json={"product_id": pid2, "quantity": 1},
        headers=customer_auth_headers,
    )
    assert add2_resp.status_code == 200
    assert add2_resp.json()["total_items"] == 3

    # 5. Update Item 1 Quantity to 5
    upd_resp = client.put(
        f"/api/v1/storefront/cart/items/{pid}",
        json={"quantity": 5},
        headers=customer_auth_headers,
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["total_items"] == 6  # 5 + 1

    # 6. Remove Item 2
    del_resp = client.delete(
        f"/api/v1/storefront/cart/items/{pid2}",
        headers=customer_auth_headers,
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["total_items"] == 5


# ------------------------------------------------------------------------------
# 4. Checkout & Order Placement
# ------------------------------------------------------------------------------

def test_storefront_checkout_and_orders(storefront_test_context, customer_auth_headers):
    pid = storefront_test_context["product_id"]

    # Ensure cart has items
    client.post(
        "/api/v1/storefront/cart/items",
        json={"product_id": pid, "quantity": 2},
        headers=customer_auth_headers,
    )

    # 1. Place Order via Checkout
    checkout_payload = {
        "delivery_type": "delivery",
        "delivery_address": "Flat 402, Green Park Residency, Pune",
        "payment_method": "cod",
        "notes": "Please call before delivery",
    }
    checkout_resp = client.post(
        "/api/v1/storefront/checkout",
        json=checkout_payload,
        headers=customer_auth_headers,
    )
    assert checkout_resp.status_code == 201
    order_data = checkout_resp.json()
    assert "order_id" in order_data
    assert "ORD-ONL-" in order_data["order_number"]
    assert order_data["status"] == "pending"
    assert order_data["delivery_type"] == "delivery"
    order_id = order_data["order_id"]

    # 2. View My Orders list
    orders_resp = client.get("/api/v1/storefront/my-orders", headers=customer_auth_headers)
    assert orders_resp.status_code == 200
    orders_body = orders_resp.json()
    orders_list = orders_body["items"]
    assert orders_body["counts"]["total"] >= 1
    assert len(orders_list) >= 1
    assert any(o["id"] == order_id for o in orders_list)

    # 3. View Order Details & Tracking
    detail_resp = client.get(f"/api/v1/storefront/my-orders/{order_id}", headers=customer_auth_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["id"] == order_id
    assert detail_data["order_number"] == order_data["order_number"]
    assert len(detail_data["items"]) >= 1


# ------------------------------------------------------------------------------
# 5. Customer Profile & Wallet
# ------------------------------------------------------------------------------

def test_storefront_profile(storefront_test_context, customer_auth_headers):
    phone = storefront_test_context["customer_phone"]

    prof_resp = client.get("/api/v1/storefront/profile", headers=customer_auth_headers)
    assert prof_resp.status_code == 200
    pdata = prof_resp.json()
    assert pdata["phone"] == phone
    assert pdata["name"] == "Rahul Ramesh Sharma"
    assert "loyalty_points" in pdata
    assert "wallet_balance" in pdata


# ------------------------------------------------------------------------------
# 6. Security Isolation (Customer cannot access Staff Admin APIs)
# ------------------------------------------------------------------------------

def test_customer_security_isolation(customer_auth_headers):
    # Customer tries to access POS cashier cart: /api/v1/billing/cart
    # Must be rejected with 401 or 403 Forbidden!
    pos_cart_resp = client.get("/api/v1/billing/cart", headers=customer_auth_headers)
    assert pos_cart_resp.status_code in (401, 403)

    # Customer tries to access store settings
    stores_resp = client.get("/api/v1/stores", headers=customer_auth_headers)
    assert stores_resp.status_code in (401, 403)


# ------------------------------------------------------------------------------
# 7. Customer Unified PIN Setup and Login Lifecycle
# ------------------------------------------------------------------------------

def test_customer_pin_setup_and_login_lifecycle(storefront_test_context, customer_auth_headers):
    phone = storefront_test_context["customer_phone"]
    customer_id = storefront_test_context["customer_id"]

    # 1. Reset auth_pin in DB to test fresh setup
    db = SessionLocal()
    try:
        cust = db.query(Customer).filter(Customer.id == customer_id).first()
        cust.auth_pin = None
        cust.pin_set_at = None
        db.commit()
    finally:
        db.close()

    # 2. Setup Initial Security PIN
    setup_resp = client.post(
        "/api/v1/auth/pin/setup",
        json={"pin": "1234"},
        headers=customer_auth_headers,
    )
    assert setup_resp.status_code == 200
    assert setup_resp.json()["success"] is True

    # 3. Duplicate PIN setup fails with 409 Conflict
    dup_resp = client.post(
        "/api/v1/auth/pin/setup",
        json={"pin": "5678"},
        headers=customer_auth_headers,
    )
    assert dup_resp.status_code == 409

    # 4. Login via Mobile + PIN
    login_resp = client.post(
        "/api/v1/auth/login/mobile-pin",
        json={"phone": phone, "pin": "1234"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "access_token" in login_data

    from app.core.security import decode_token
    payload = decode_token(login_data["access_token"])
    assert payload["role"] == "customer"
    assert payload["customer_id"] == customer_id

    # 5. Wrong PIN fails with 401
    wrong_resp = client.post(
        "/api/v1/auth/login/mobile-pin",
        json={"phone": phone, "pin": "0000"},
    )
    assert wrong_resp.status_code == 401

    # 6. Change PIN
    pin_headers = {"Authorization": f"Bearer {login_data['access_token']}"}
    change_resp = client.post(
        "/api/v1/auth/pin/change",
        json={"current_pin": "1234", "new_pin": "5678"},
        headers=pin_headers,
    )
    assert change_resp.status_code == 200

    # 7. Login with old PIN fails
    old_resp = client.post(
        "/api/v1/auth/login/mobile-pin",
        json={"phone": phone, "pin": "1234"},
    )
    assert old_resp.status_code == 401

    # 8. Login with new PIN succeeds
    new_resp = client.post(
        "/api/v1/auth/login/mobile-pin",
        json={"phone": phone, "pin": "5678"},
    )
    assert new_resp.status_code == 200

