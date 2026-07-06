import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers():
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "productsTest",
            "slug": "prodtest",
            "email": "prod@test.com",
            "admin_name": "Prod Admin",
            "password": "testpass123",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "prod@test.com", "password": "testpass123"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_and_list_products(auth_headers):
    create_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Test Product",
            "sku": "TEST-001",
            "price": "99.99",
            "gst_rate": "18.00",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    products= create_resp.json()
    assert product["sku"] == "TEST-001"

    list_resp = client.get("/api/v1/products", headers=auth_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1
