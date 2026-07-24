import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def billing_setup(unique_slug):
    email = f"bill-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Billing Test",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Bill Admin",
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
        json={"name": "Billing Store", "code": "BS1"},
        headers=headers,
    ).json()

    product = client.post(
        "/api/v1/products",
        json={
            "name": "Billing Product",
            "sku": "BILL-001",
            "price": "200.00",
            "gst_rate": "18.00",
            "hsn_code": "6109",
        },
        headers=headers,
    ).json()

    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product["id"], "quantity": 100},
        headers=headers,
    )

    return headers, store, product


def test_cart_add_and_gst_totals(billing_setup):
    headers, store, product = billing_setup

    add_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"], "same_state": True},
        json={"product_id": product["id"], "quantity": "2"},
        headers=headers,
    )
    assert add_resp.status_code == 200
    cart = add_resp.json()
    assert len(cart["items"]) == 1
    assert cart["subtotal"] == "400.00"
    assert cart["gst_amount"] == "72.00"
    assert cart["grand_total"] == "472.00"

    get_resp = client.get("/api/v1/billing/cart", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["grand_total"] == "472.00"


def test_cart_apply_discount(billing_setup):
    headers, store, product = billing_setup

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    discount_resp = client.post(
        "/api/v1/billing/cart/apply-discount",
        json={"discount_type": "percentage", "value": "10"},
        headers=headers,
    )
    assert discount_resp.status_code == 200
    cart = discount_resp.json()
    assert cart["discount_amount"] == "20.00"
    assert cart["grand_total"] == "216.00"


def test_checkout_split_payment_and_search(billing_setup):
    headers, store, product = billing_setup

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )

    invoice_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "same_state": True,
            "payments": [
                {"payment_mode": "cash", "amount": "100.00"},
                {"payment_mode": "upi", "amount": "136.00", "transaction_reference": "UPI123"},
            ],
        },
        headers=headers,
    )
    assert invoice_resp.status_code == 201
    invoice = invoice_resp.json()
    assert invoice["invoice_number"].startswith("INV-")
    assert invoice["total_amount"] == "236.00"

    search_resp = client.get(
        "/api/v1/invoices",
        params={"invoice_number": invoice["invoice_number"]},
        headers=headers,
    )
    assert search_resp.status_code == 200
    assert len(search_resp.json()) >= 1


def test_invoice_pdf_download(billing_setup):
    headers, store, product = billing_setup

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    invoice = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "payments": [{"payment_mode": "cash", "amount": "236.00"}],
        },
        headers=headers,
    ).json()

    pdf_resp = client.get(
        f"/api/v1/invoices/{invoice['id']}/pdf",
        headers=headers,
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content[:4] == b"%PDF"


def test_refund_approval_creates_credit_note(billing_setup):
    headers, store, product = billing_setup

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    invoice = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "payments": [{"payment_mode": "cash", "amount": "236.00"}],
        },
        headers=headers,
    ).json()

    refund_resp = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "100.00",
            "refund_method": "cash",
            "reason": "Partial return",
        },
        headers=headers,
    )
    assert refund_resp.status_code == 201
    refund = refund_resp.json()
    assert refund["status"] == "pending"

    approve_resp = client.post(
        f"/api/v1/refunds/{refund['id']}/approve",
        headers=headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    cn_resp = client.get(
        "/api/v1/credit-notes",
        params={"invoice_id": invoice["id"]},
        headers=headers,
    )
    assert cn_resp.status_code == 200
    credit_notes = cn_resp.json()
    assert len(credit_notes) == 1
    assert credit_notes[0]["credit_note_no"].startswith("CN-")
    assert credit_notes[0]["refund_amount"] == "100.00"
    assert credit_notes[0]["cgst_amount"] != "0.00" or credit_notes[0]["sgst_amount"] != "0.00"


def _inventory_qty(headers, store_id, product_id):
    rows = client.get(
        "/api/v1/inventory",
        params={"store_id": store_id},
        headers=headers,
    ).json()
    match = next((r for r in rows if r["product_id"] == product_id), None)
    return match["quantity"] if match else 0


def test_return_restores_inventory(billing_setup):
    headers, store, product = billing_setup

    qty_before = _inventory_qty(headers, store["id"], product["id"])

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "2"},
        headers=headers,
    )
    invoice = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "payments": [{"payment_mode": "cash", "amount": "472.00"}],
        },
        headers=headers,
    ).json()

    inv_after_sale = _inventory_qty(headers, store["id"], product["id"])
    assert inv_after_sale == qty_before - 2

    return_resp = client.post(
        "/api/v1/billing/returns",
        json={
            "invoice_id": invoice["id"],
            "product_id": product["id"],
            "return_quantity": "1",
            "reason": "Customer exchange",
        },
        headers=headers,
    )
    assert return_resp.status_code == 200

    inv_after_return = _inventory_qty(headers, store["id"], product["id"])
    assert inv_after_return == qty_before - 1


def test_daily_billing_closure_report(billing_setup):
    headers, store, product = billing_setup

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "payments": [{"payment_mode": "cash", "amount": "236.00"}],
        },
        headers=headers,
    )

    report = client.get("/api/v1/reports/daily-billing", headers=headers).json()
    assert report["invoice_count"] >= 1
    assert "card_sales" in report
    assert "wallet_sales" in report
    assert "discount_amount" in report
    assert report["cash_sales"] >= 236.0


def test_invoice_search_by_gstin_and_payment_status(billing_setup):
    headers, store, product = billing_setup

    customer = client.post(
        "/api/v1/customers",
        json={
            "name": "GST Customer",
            "phone": "9876543210",
            "gstin": "27AAAAA0000A1Z5",
        },
        headers=headers,
    ).json()

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    invoice = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "customer_id": customer["id"],
            "payments": [{"payment_mode": "upi", "amount": "236.00"}],
        },
        headers=headers,
    ).json()

    by_gstin = client.get(
        "/api/v1/invoices",
        params={"gstin": "27AAAAA0000A1Z5"},
        headers=headers,
    ).json()
    assert any(i["id"] == invoice["id"] for i in by_gstin)

    by_payment = client.get(
        "/api/v1/invoices",
        params={"payment_status": "completed"},
        headers=headers,
    ).json()
    assert any(i["id"] == invoice["id"] for i in by_payment)


