import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def invoice_pdf_setup(unique_slug):
    email = f"pdf-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Invoice PDF Tenant",
            "slug": unique_slug,
            "email": email,
            "admin_name": "PDF Admin",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": "PDF Store", "code": f"P{unique_slug[:3]}"},
        headers=headers,
    ).json()

    product = client.post(
        "/api/v1/products",
        json={
            "name": "PDF Item",
            "sku": f"SKU-{unique_slug[:4]}",
            "price": "150.00",
            "gst_rate": "18.00",
            "hsn_code": "6109",
        },
        headers=headers,
    ).json()

    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product["id"], "quantity": 50},
        headers=headers,
    )

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"], "same_state": True},
        json={"product_id": product["id"], "quantity": "2"},
        headers=headers,
    )

    invoice = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "same_state": True,
            "payments": [{"payment_mode": "cash", "amount": "354.00"}],
        },
        headers=headers,
    ).json()

    return headers, store, invoice, unique_slug


def test_invoice_pdf_download_endpoint(invoice_pdf_setup):
    headers, store, invoice, slug = invoice_pdf_setup
    invoice_id = invoice["id"]

    resp = client.get(
        f"/api/v1/invoices/{invoice_id}/pdf?mode=download",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert f"{invoice['invoice_number']}.pdf" in resp.headers.get("content-disposition", "")

    pdf_bytes = resp.content
    assert pdf_bytes.startswith(b"%PDF-1.")
    assert b"%%EOF" in pdf_bytes
    assert b"/Catalog" in pdf_bytes
    assert b"TAX INVOICE" in pdf_bytes
    assert invoice["invoice_number"].encode() in pdf_bytes


def test_invoice_pdf_preview_endpoint(invoice_pdf_setup):
    headers, store, invoice, slug = invoice_pdf_setup
    invoice_id = invoice["id"]

    resp = client.get(
        f"/api/v1/invoices/{invoice_id}/pdf?mode=preview",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "inline" in resp.headers.get("content-disposition", "")


def test_invoice_pdf_unauthenticated(invoice_pdf_setup):
    _, _, invoice, _ = invoice_pdf_setup
    resp = client.get(f"/api/v1/invoices/{invoice['id']}/pdf")
    assert resp.status_code == 401


def test_invoice_pdf_tenant_isolation(invoice_pdf_setup):
    headers, store, invoice, slug = invoice_pdf_setup

    # Register another tenant
    other_slug = f"other-{slug}"
    other_email = f"other-{slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Other Tenant",
            "slug": other_slug,
            "email": other_email,
            "admin_name": "Other Admin",
            "password": "Password123!",
        },
    )
    other_login = client.post(
        "/api/v1/auth/login",
        json={"email": other_email, "password": "Password123!"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    # Attempt to access first tenant's invoice PDF with other tenant's credentials
    resp = client.get(
        f"/api/v1/invoices/{invoice['id']}/pdf",
        headers=other_headers,
    )
    assert resp.status_code == 404
