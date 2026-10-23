import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers(unique_slug):
    email = f"prod-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "productsTest",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Prod Admin",
            "password": "testpass123",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
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
    product = create_resp.json()
    assert product["sku"] == "TEST-001"

    list_resp = client.get("/api/v1/products", headers=auth_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


def test_search_products(auth_headers):
    # 1. Create product for searching
    create_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Wireless Mouse",
            "sku": "WM-9001",
            "barcode": "8901234567890",
            "price": "499.00",
            "gst_rate": "18.00",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    # 2. Search by partial name -> 200 with result
    search_name = client.get(
        "/api/v1/products/search?search=Wireless&page=1&page_size=100",
        headers=auth_headers,
    )
    assert search_name.status_code == 200
    items = search_name.json()
    assert isinstance(items, list)
    assert any(p["name"] == "Wireless Mouse" for p in items)

    # 3. Search by SKU -> 200 with result
    search_sku = client.get(
        "/api/v1/products/search?search=WM-9001&page=1&page_size=100",
        headers=auth_headers,
    )
    assert search_sku.status_code == 200
    assert any(p["sku"] == "WM-9001" for p in search_sku.json())

    # 4. Search by barcode -> 200 with result
    search_bc = client.get(
        "/api/v1/products/search?search=8901234567890&page=1&page_size=100",
        headers=auth_headers,
    )
    assert search_bc.status_code == 200
    assert any(p["barcode"] == "8901234567890" for p in search_bc.json())

    # 5. Search zero matches (e.g. 'ca' or 'nonexistent') -> 200 with empty list []
    search_zero = client.get(
        "/api/v1/products/search?search=ca&page=1&page_size=100",
        headers=auth_headers,
    )
    assert search_zero.status_code == 200
    assert search_zero.json() == []

    search_none = client.get(
        "/api/v1/products/search?search=nonexistent_xyz&page=1&page_size=100",
        headers=auth_headers,
    )
    assert search_none.status_code == 200
    assert search_none.json() == []

    # 6. Search validation (< 2 characters) -> 422
    search_short = client.get(
        "/api/v1/products/search?search=p&page=1&page_size=100",
        headers=auth_headers,
    )
    assert search_short.status_code == 422
