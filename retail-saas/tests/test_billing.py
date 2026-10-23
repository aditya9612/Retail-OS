from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.product import Product

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
    assert cart["items"][0]["product_name"] == product["name"]
    assert Decimal(str(cart["items"][0]["quantity"])) == Decimal("2")
    assert cart["items"][0]["unit_price"] == "200.00"
    assert cart["items"][0]["total_amount"] == "472.00"
    assert cart["subtotal"] == "400.00"
    assert cart["gst_amount"] == "72.00"
    assert cart["grand_total"] == "472.00"

    get_resp = client.get("/api/v1/billing/cart", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["grand_total"] == "472.00"


def test_cart_price_override_cannot_be_below_product_cost(billing_setup):
    headers, store, product = billing_setup
    db = SessionLocal()
    try:
        db.query(Product).filter(Product.id == product["id"]).update(
            {Product.cost_price: Decimal("100.00")}
        )
        db.commit()
    finally:
        db.close()

    below_cost = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={
            "product_id": product["id"],
            "quantity": "1",
            "unit_price": "99.99",
        },
        headers=headers,
    )
    assert below_cost.status_code == 400
    assert "cannot be lower than product cost price" in below_cost.text

    at_cost = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={
            "product_id": product["id"],
            "quantity": "1",
            "unit_price": "100.00",
        },
        headers=headers,
    )
    assert at_cost.status_code == 200, at_cost.text


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


def test_cart_apply_discount_validates_coupon_and_uses_configured_value(
    billing_setup,
):
    from datetime import date, timedelta

    headers, store, product = billing_setup
    today = date.today()
    coupon_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "CART10A",
            "description": "Cart percentage discount",
            "discount_type": "percentage",
            "discount_value": "10",
            "minimum_order_amount": "1.00",
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
        },
        headers=headers,
    )
    assert coupon_resp.status_code == 201, coupon_resp.text

    add_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    assert add_resp.status_code == 200, add_resp.text

    invalid_coupon = client.post(
        "/api/v1/billing/cart/apply-discount",
        json={
            "discount_type": "coupon",
            "value": "0",
            "coupon_code": "INVALID1",
        },
        headers=headers,
    )
    assert invalid_coupon.status_code >= 400

    valid_coupon = client.post(
        "/api/v1/billing/cart/apply-discount",
        json={
            "discount_type": "coupon",
            "value": "0",
            "coupon_code": "CART10A",
        },
        headers=headers,
    )
    assert valid_coupon.status_code == 200, valid_coupon.text
    assert valid_coupon.json()["discount_amount"] == "20.00"
    assert valid_coupon.json()["coupon_code"] == "CART10A"


def test_invoice_response_includes_request_details_and_refund_print_state(
    billing_setup,
):
    headers, store, product = billing_setup
    add_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store["id"]},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    assert add_resp.status_code == 200, add_resp.text

    invoice_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "same_state": True,
            "payments": [
                {
                    "payment_mode": "cash",
                    "amount": "236.00",
                    "amount_tendered": "240.00",
                    "change_due": "4.00",
                }
            ],
        },
        headers=headers,
    )
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice = invoice_resp.json()

    assert invoice["pdf_url"] == f"/api/v1/invoices/{invoice['id']}/pdf"
    assert invoice["customer_id"] is None
    assert invoice["same_state"] is True
    assert invoice["items"][0]["product_id"] == product["id"]
    assert Decimal(str(invoice["items"][0]["quantity"])) == Decimal("1")
    assert invoice["items"][0]["unit_price"] == "200.00"
    payment = invoice["payments"][0]
    assert payment["payment_mode"] == "cash"
    assert payment["amount_tendered"] == "240.00"
    assert payment["change_due"] == "4.00"

    db = SessionLocal()
    try:
        saved_invoice = db.get(Invoice, invoice["id"])
        saved_invoice.status = "refunded"
        db.commit()
    finally:
        db.close()

    reprint_resp = client.post(
        f"/api/v1/invoices/{invoice['id']}/reprint",
        json={"printer_type": "generic"},
        headers=headers,
    )
    assert reprint_resp.status_code == 200, reprint_resp.text
    assert "Paid via: Refunded" in reprint_resp.json()["print_payload"]["payload"]


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
    assert "--" not in invoice["invoice_number"]
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
            "address": "123 Market Road, Mumbai",
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


def test_create_invoice_direct_items(billing_setup):
    headers, store, product = billing_setup

    resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "same_state": True,
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 2,
                    "unit_price": "200.00",
                    "discount": "0.00",
                }
            ],
            "payments": [
                {
                    "payment_mode": "cash",
                    "amount": "472.00",
                    "transaction_reference": "TXN_DIRECT",
                }
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["invoice_number"].startswith("INV-")
    assert data["total_amount"] == "472.00"
    assert data["subtotal"] == "400.00"
    assert data["cgst_amount"] == "36.00"
    assert data["sgst_amount"] == "36.00"
