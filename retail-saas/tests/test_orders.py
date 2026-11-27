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


def test_list_orders_handles_null_tax_and_roundoff_decimals(setup_order_flow):
    headers, store, product = setup_order_flow
    from app.core.database import SessionLocal
    from app.models.order import Order
    from app.models.user import User
    from decimal import Decimal
    import uuid

    db = SessionLocal()
    user = db.query(User).filter(User.store_id == store['id']).first() or db.query(User).first()
    raw_order = Order(
        tenant_id=user.tenant_id,
        store_id=store['id'],
        order_number=f"ORD-NULL-{uuid.uuid4().hex[:6].upper()}",
        order_type="pos",
        status="confirmed",
        subtotal=Decimal("500.00"),
        total_amount=Decimal("500.00"),
    )
    raw_order.cgst_amount = None
    raw_order.sgst_amount = None
    raw_order.igst_amount = None
    raw_order.round_off = None
    db.add(raw_order)
    db.commit()
    db.refresh(raw_order)
    order_id = raw_order.id
    db.close()

    res = client.get("/api/v1/orders?page=1&page_size=20", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["items"], list)
    assert body["counts"]["total"] >= len(body["items"])
    orders = body["items"]
    target = next((o for o in orders if o["id"] == order_id), None)
    if target:
        assert Decimal(str(target["cgst_amount"])) == Decimal("0.00")
        assert Decimal(str(target["sgst_amount"])) == Decimal("0.00")
        assert Decimal(str(target["round_off"])) == Decimal("0.00")


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


def test_order_payment_method_validation_and_persistence(setup_order_flow):
    headers, store, product = setup_order_flow

    # 1. Valid payment method: "cod" (e.g., e-commerce order)
    resp_cod = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "ecommerce",
            "payment_method": "cod",
            "delivery_address": "Sainath Nagar, Nashik, Maharashtra 462456",
            "delivery_pincode": "462456",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert resp_cod.status_code == 201, resp_cod.text
    order_cod = resp_cod.json()
    assert order_cod["payment_method"] == "cod"
    assert order_cod["payment_status"] == "pending"
    assert order_cod["order_type"] == "ecommerce"

    # 2. Case-insensitive and trimmed: "  UPI  " -> "upi"
    resp_upi = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "pos",
            "payment_method": "  UPI  ",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert resp_upi.status_code == 201, resp_upi.text
    order_upi = resp_upi.json()
    assert order_upi["payment_method"] == "upi"

    # 3. None / omitted payment_method defaults to None
    resp_none = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "pos",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert resp_none.status_code == 201, resp_none.text
    assert resp_none.json()["payment_method"] is None

    # 4. Update order payment_method via PATCH
    update_resp = client.patch(
        f"/api/v1/orders/{order_cod['id']}",
        json={"payment_method": "card"},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["payment_method"] == "card"

    # 5. Invalid payment_method rejected with 422:
    invalid_payment_methods = [
        "",
        "   ",
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "n/a",
        "na",
        "12233",
        "123",
        "@@#$%",
        "!@#$",
        "ppppp",
        "-----",
        "[[[]]]",
        '>?"{P:><L:"{:.',
        "nausomd",
        "HTDFFGHGKGKHK",
        12345,
        True,
    ]

    for bad_method in invalid_payment_methods:
        bad_post = client.post(
            "/api/v1/orders",
            json={
                "store_id": store["id"],
                "order_type": "ecommerce",
                "payment_method": bad_method,
                "items": [{"product_id": product["id"], "quantity": 1}],
            },
            headers=headers,
        )
        assert bad_post.status_code == 422, f"Expected 422 for bad payment_method '{bad_method}', got {bad_post.status_code}: {bad_post.text}"

        bad_patch = client.patch(
            f"/api/v1/orders/{order_cod['id']}",
            json={"payment_method": bad_method},
            headers=headers,
        )
        assert bad_patch.status_code == 422, f"Expected 422 on PATCH for bad payment_method '{bad_method}', got {bad_patch.status_code}: {bad_patch.text}"


def test_order_delivery_status_validation_and_persistence(setup_order_flow):
    headers, store, product = setup_order_flow

    # 1. E-commerce order with delivery address automatically gets delivery_status='pending'
    resp_ecom = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "ecommerce",
            "delivery_address": "Sainath Nagar, Nashik, Maharashtra 462456",
            "delivery_pincode": "462456",
            "payment_method": "cod",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert resp_ecom.status_code == 201, resp_ecom.text
    order_ecom = resp_ecom.json()
    assert order_ecom["delivery_status"] == "pending"
    assert order_ecom["delivery_address"] == "Sainath Nagar, Nashik, Maharashtra 462456"
    assert order_ecom["delivery_pincode"] == "462456"

    # 2. In-store POS order without delivery address returns delivery_status=None (null in JSON)
    resp_pos = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "pos",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert resp_pos.status_code == 201, resp_pos.text
    assert resp_pos.json()["delivery_status"] is None

    # 3. Explicit valid delivery_status with whitespace and casing: '  OUT_FOR_DELIVERY  ' -> 'out_for_delivery'
    resp_explicit = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "order_type": "ecommerce",
            "delivery_address": "Flat 101, MG Road, Pune 411001",
            "delivery_status": "  OUT_FOR_DELIVERY  ",
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    )
    assert resp_explicit.status_code == 201, resp_explicit.text
    assert resp_explicit.json()["delivery_status"] == "out_for_delivery"

    # 4. Update delivery_status via PATCH
    patch_resp = client.patch(
        f"/api/v1/orders/{order_ecom['id']}",
        json={"delivery_status": "delivered"},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["delivery_status"] == "delivered"

    # 5. Confirm order preserves delivery and does not create duplicates
    confirm_resp = client.post(f"/api/v1/orders/{order_ecom['id']}/confirm", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["status"] == "confirmed"

    # 6. Reject invalid delivery_status random data with 422:
    invalid_delivery_statuses = [
        "",
        "   ",
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "n/a",
        "na",
        "12233",
        "123",
        "@@#$%",
        "!@#$",
        "ppppp",
        "-----",
        "[[[]]]",
        '>?"{P:><L:"{:.',
        "nausomd",
        "HTDFFGHGKGKHK",
        12345,
        True,
    ]

    for bad_status in invalid_delivery_statuses:
        bad_post = client.post(
            "/api/v1/orders",
            json={
                "store_id": store["id"],
                "order_type": "ecommerce",
                "delivery_address": "Some Valid Address, Pune 411001",
                "delivery_status": bad_status,
                "items": [{"product_id": product["id"], "quantity": 1}],
            },
            headers=headers,
        )
        assert bad_post.status_code == 422, f"Expected 422 for bad delivery_status '{bad_status}', got {bad_post.status_code}: {bad_post.text}"

        bad_patch = client.patch(
            f"/api/v1/orders/{order_ecom['id']}",
            json={"delivery_status": bad_status},
            headers=headers,
        )
        assert bad_patch.status_code == 422, f"Expected 422 on PATCH for bad delivery_status '{bad_status}', got {bad_patch.status_code}: {bad_patch.text}"


def test_order_item_variant_validation_and_persistence(setup_order_flow):
    headers, store, product = setup_order_flow

    # Create a product variant
    var_resp = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={
            "variant_name": "pp",
            "sku": "TSHIRT-V1-PP",
            "selling_price": 500,
        },
        headers=headers,
    )
    assert var_resp.status_code in (200, 201), f"Variant create failed: {var_resp.text}"
    variant = var_resp.json()

    # 1. Test creating order with explicit variant "pp" and variant_id
    order_req = {
        "store_id": store["id"],
        "order_type": "ecommerce",
        "delivery_address": "sainath nagar, nashik 422001",
        "delivery_pincode": "462456",
        "same_state": True,
        "items": [
            {
                "product_id": product["id"],
                "quantity": 1,
                "unit_price": 500,
                "discount": 0,
                "variant": "pp",
                "variant_id": variant["id"],
            }
        ],
    }

    create_resp = client.post(
        "/api/v1/orders",
        json=order_req,
        headers=headers,
    )
    assert create_resp.status_code == 201, f"Order create failed: {create_resp.text}"
    order_data = create_resp.json()
    assert len(order_data["items"]) == 1
    assert order_data["items"][0]["variant"] == "pp"
    assert order_data["items"][0]["variant_id"] == variant["id"]

    # 2. Verify GET /api/v1/orders/{id} persists the variant
    get_resp = client.get(
        f"/api/v1/orders/{order_data['id']}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["items"][0]["variant"] == "pp"
    assert get_data["items"][0]["variant_id"] == variant["id"]

    # 3. Test creating order with variant_id only (auto-resolve variant_name)
    order_req2 = {
        "store_id": store["id"],
        "order_type": "pos",
        "items": [
            {
                "product_id": product["id"],
                "quantity": 1,
                "unit_price": 500,
                "variant_id": variant["id"],
            }
        ],
    }
    create_resp2 = client.post(
        "/api/v1/orders",
        json=order_req2,
        headers=headers,
    )
    assert create_resp2.status_code == 201, f"Order create 2 failed: {create_resp2.text}"
    order_data2 = create_resp2.json()
    assert order_data2["items"][0]["variant"] == "pp"

    # 4. Test creating order with text variant only (e.g., "XL")
    order_req3 = {
        "store_id": store["id"],
        "order_type": "pos",
        "items": [
            {
                "product_id": product["id"],
                "quantity": 1,
                "unit_price": 500,
                "variant": "XL",
            }
        ],
    }
    create_resp3 = client.post(
        "/api/v1/orders",
        json=order_req3,
        headers=headers,
    )
    assert create_resp3.status_code == 201, f"Order create 3 failed: {create_resp3.text}"
    assert create_resp3.json()["items"][0]["variant"] == "XL"

    # 5. Reject invalid random variant inputs with 422:
    invalid_variants = [
        "",
        "   ",
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "n/a",
        "na",
        "12233",
        "123",
        "@@#$%",
        "!@#$",
        "ppppp",
        "-----",
        "[[[]]]",
        '>?"{P:><L:"{:.',
        "nausomd",
        "HTDFFGHGKGKHK",
        12345,
        True,
    ]

    for bad_v in invalid_variants:
        bad_req = {
            "store_id": store["id"],
            "order_type": "pos",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                    "unit_price": 500,
                    "variant": bad_v,
                }
            ],
        }
        bad_resp = client.post(
            "/api/v1/orders",
            json=bad_req,
            headers=headers,
        )
        assert bad_resp.status_code == 422, f"Expected 422 for bad variant '{bad_v}', got {bad_resp.status_code}: {bad_resp.text}"



