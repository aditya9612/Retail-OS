import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def setup_order_flow():
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Order Test",
            "slug": "ordtest",
            "email": "order@test.com",
            "admin_name": "Order Admin",
            "password": "testpass123",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "order@test.com", "password": "testpass123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": "Test Store", "code": "TS1"},
        headers=headers,
    ).json()

    products= client.post(
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
    headers, store, products= setup_order_flow

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
