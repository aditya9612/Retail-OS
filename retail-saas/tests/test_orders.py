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
        json={"name": "Order Product", "sku": "ORD-001", "price": "100.00"},
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
    orders = res.json()
    assert isinstance(orders, list)
    target = next((o for o in orders if o["id"] == order_id), None)
    if target:
        assert Decimal(str(target["cgst_amount"])) == Decimal("0.00")
        assert Decimal(str(target["sgst_amount"])) == Decimal("0.00")
        assert Decimal(str(target["round_off"])) == Decimal("0.00")
