import random
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture(scope="module")
def invoice_test_fixture():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # 1. Register Tenant
        owner_email = f"inv_owner_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"SuperStore {suffix}",
                "domain": f"inv-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Owner {suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_res.status_code == 200, reg_res.text
        tenant_id = reg_res.json()["tenant_id"]

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": owner_pass},
        )
        assert login_res.status_code == 200
        owner_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. Create Store 1 & Store 2
        s1 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Store A {suffix}", "code": f"STA_{suffix}", "city": "Pune", "state": "Maharashtra"},
        )
        assert s1.status_code == 201, s1.text
        store1_id = s1.json()["id"]

        s2 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Store B {suffix}", "code": f"STB_{suffix}", "city": "Mumbai", "state": "Maharashtra"},
        )
        assert s2.status_code == 201, s2.text
        store2_id = s2.json()["id"]

        # 3. Create Cashier 1 at Store 1
        c1_email = f"cashier1_{suffix}@retailtest.com"
        c1_pass = "CashierPass123!"
        u1_res = client.post(
            "/api/v1/users",
            headers=owner_headers,
            data={
                "email": c1_email,
                "full_name": "Cashier One",
                "phone": _gen_phone(),
                "password": c1_pass,
                "role": "cashier",
            },
        )
        assert u1_res.status_code == 201, u1_res.text
        c1_id = u1_res.json()["id"]
        client.patch(f"/api/v1/users/{c1_id}/assign-store", headers=owner_headers, json={"store_id": store1_id})
        c1_login = client.post("/api/v1/auth/login", json={"email": c1_email, "password": c1_pass})
        cashier1_headers = {"Authorization": f"Bearer {c1_login.json()['access_token']}"}

        # 4. Create Cashier 2 at Store 2
        c2_email = f"cashier2_{suffix}@retailtest.com"
        c2_pass = "CashierPass123!"
        u2_res = client.post(
            "/api/v1/users",
            headers=owner_headers,
            data={
                "email": c2_email,
                "full_name": "Cashier Two",
                "phone": _gen_phone(),
                "password": c2_pass,
                "role": "cashier",
            },
        )
        assert u2_res.status_code == 201, u2_res.text
        c2_id = u2_res.json()["id"]
        client.patch(f"/api/v1/users/{c2_id}/assign-store", headers=owner_headers, json={"store_id": store2_id})
        c2_login = client.post("/api/v1/auth/login", json={"email": c2_email, "password": c2_pass})
        cashier2_headers = {"Authorization": f"Bearer {c2_login.json()['access_token']}"}

        # 5. Create Products
        p1 = client.post(
            "/api/v1/products",
            headers=owner_headers,
            json={
                "name": f"Item Alpha {suffix}",
                "sku": f"SKU-A-{suffix}",
                "price": "100.00",
                "selling_price": "100.00",
                "cost_price": "60.00",
                "gst_rate": "18.00",
                "hsn_code": "1234",
            },
        ).json()

        # 6. Add stock at Store 1
        client.post(
            "/api/v1/inventory/stock-in",
            headers=owner_headers,
            json={"store_id": store1_id, "product_id": p1["id"], "quantity": 50},
        )

        return {
            "tenant_id": tenant_id,
            "owner_headers": owner_headers,
            "store1_id": store1_id,
            "store2_id": store2_id,
            "cashier1_headers": cashier1_headers,
            "cashier2_headers": cashier2_headers,
            "product_id": p1["id"],
        }
    finally:
        db.close()


def test_get_invoice_by_number_and_pdf_status(invoice_test_fixture):
    ctx = invoice_test_fixture

    # Cashier 1 bills an item
    inv_res = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 2, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "236.00"}],
        },
    )
    assert inv_res.status_code == 201
    invoice = inv_res.json()
    inv_num = invoice["invoice_number"]

    # 1. Lookup by number
    by_num_res = client.get(
        f"/api/v1/invoices/by-number/{inv_num}",
        headers=ctx["cashier1_headers"],
    )
    assert by_num_res.status_code == 200
    assert by_num_res.json()["id"] == invoice["id"]
    assert by_num_res.json()["invoice_number"] == inv_num

    # 2. Lookup by non-existent number -> 404
    bad_res = client.get(
        "/api/v1/invoices/by-number/INV-NON-EXISTENT-999",
        headers=ctx["cashier1_headers"],
    )
    assert bad_res.status_code == 404

    # 3. Cashier 2 (Store 2) cannot lookup Store 1 invoice by number -> 403
    cross_res = client.get(
        f"/api/v1/invoices/by-number/{inv_num}",
        headers=ctx["cashier2_headers"],
    )
    assert cross_res.status_code == 403

    # 4. Check PDF status endpoint
    status_res = client.get(
        f"/api/v1/invoices/{invoice['id']}/pdf-status",
        headers=ctx["cashier1_headers"],
    )
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["status"] == "ready"
    assert "pdf_url" in st_data
    assert st_data["invoice_number"] == inv_num


def test_reprint_invoice_includes_duplicate_watermark(invoice_test_fixture):
    ctx = invoice_test_fixture

    # Create invoice
    inv = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 1, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
        },
    ).json()

    # Call reprint
    reprint_res = client.post(
        f"/api/v1/invoices/{inv['id']}/reprint",
        headers=ctx["cashier1_headers"],
        json={"printer_type": "generic"},
    )
    assert reprint_res.status_code == 200
    data = reprint_res.json()
    assert "print_payload" in data
    # Watermark check
    payload_str = data["print_payload"]["payload"]
    assert "*** DUPLICATE / REPRINT ***" in payload_str


def test_void_invoice_restores_inventory_and_cancels_payments(invoice_test_fixture):
    ctx = invoice_test_fixture
    db = SessionLocal()

    try:
        # Check initial inventory quantity
        inv_record = db.query(Inventory).filter(
            Inventory.store_id == ctx["store1_id"],
            Inventory.product_id == ctx["product_id"],
        ).first()
        qty_start = inv_record.quantity

        # Create invoice for 3 units
        create_res = client.post(
            "/api/v1/invoices",
            headers=ctx["cashier1_headers"],
            json={
                "store_id": ctx["store1_id"],
                "same_state": True,
                "items": [{"product_id": ctx["product_id"], "quantity": 3, "unit_price": "100.00"}],
                "payments": [{"payment_mode": "cash", "amount": "354.00"}],
            },
        )
        assert create_res.status_code == 201
        invoice = create_res.json()

        db.refresh(inv_record)
        assert inv_record.quantity == qty_start - 3

        # Cashier 2 from Store 2 attempts to void -> 403 Forbidden
        cross_void = client.post(
            f"/api/v1/invoices/{invoice['id']}/void",
            headers=ctx["cashier2_headers"],
            json={"reason": "Attempt unauthorized void"},
        )
        assert cross_void.status_code == 403

        # Cashier 1 voids the invoice
        void_res = client.post(
            f"/api/v1/invoices/{invoice['id']}/void",
            headers=ctx["cashier1_headers"],
            json={"reason": "Wrong billing customer cancelled"},
        )
        assert void_res.status_code == 200
        voided_inv = void_res.json()
        assert voided_inv["status"] == "cancelled"

        # Verify stock was restored back to initial
        db.refresh(inv_record)
        assert inv_record.quantity == qty_start

        # Verify payment is cancelled
        payment = db.query(Payment).filter(Payment.invoice_id == invoice["id"]).first()
        assert payment.status == "cancelled"

        # Voiding already voided invoice -> 409 Conflict
        second_void = client.post(
            f"/api/v1/invoices/{invoice['id']}/void",
            headers=ctx["cashier1_headers"],
            json={"reason": "Again void"},
        )
        assert second_void.status_code == 409

    finally:
        db.close()


def test_search_invoices_flexible_status_and_pagination(invoice_test_fixture):
    ctx = invoice_test_fixture

    # Create an invoice
    inv = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 1, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
        },
    ).json()

    # Search with payment_status="paid"
    res_paid = client.get(
        "/api/v1/invoices?payment_status=paid",
        headers=ctx["cashier1_headers"],
    )
    assert res_paid.status_code == 200
    paid_items = res_paid.json()
    assert any(i["id"] == inv["id"] for i in paid_items)

    # Search with pagination (page=1, page_size=2)
    res_paginated = client.get(
        "/api/v1/invoices?payment_status=paid&page=1&page_size=2",
        headers=ctx["cashier1_headers"],
    )
    assert res_paginated.status_code == 200
    assert len(res_paginated.json()) <= 2


def test_checkout_idempotency_key(invoice_test_fixture):
    ctx = invoice_test_fixture
    idem_key = f"IDEM-{uuid.uuid4().hex}"

    # First checkout call
    res1 = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 1, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
            "idempotency_key": idem_key,
        },
    )
    assert res1.status_code == 201
    inv1 = res1.json()

    # Retry checkout with same idempotency key
    res2 = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 1, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
            "idempotency_key": idem_key,
        },
    )
    assert res2.status_code in (200, 201)
    inv2 = res2.json()

    # Must return the SAME invoice, not duplicate
    assert inv1["id"] == inv2["id"]
    assert inv1["invoice_number"] == inv2["invoice_number"]



def test_invoice_thermal_all_modes(invoice_test_fixture):
    ctx = invoice_test_fixture

    # Create an invoice
    inv_res = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 2, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "236.00"}],
        },
    )
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["id"]
    inv_num = inv_res.json()["invoice_number"]

    # 1. Preview Mode -> PNG binary image
    res_preview = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=preview",
        headers=ctx["cashier1_headers"],
    )
    assert res_preview.status_code == 200
    assert "image/png" in res_preview.headers["content-type"]
    assert res_preview.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert res_preview.headers.get("x-invoice-print-type") == "80mm-PNG-Preview"

    # 2. View Mode -> HTML with auto-print script
    res_view = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=view",
        headers=ctx["cashier1_headers"],
    )
    assert res_view.status_code == 200
    assert "text/html" in res_view.headers["content-type"]
    assert "window.print()" in res_view.text
    assert inv_num in res_view.text

    # 3. Download Mode -> ESC/POS text attachment
    res_dl = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=download",
        headers=ctx["cashier1_headers"],
    )
    assert res_dl.status_code == 200
    assert "text/plain" in res_dl.headers["content-type"]
    assert "attachment" in res_dl.headers.get("content-disposition", "")
    assert ".txt" in res_dl.headers.get("content-disposition", "")
    assert inv_num in res_dl.text

    # 4. PDF Mode -> 80mm PDF attachment
    res_pdf = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=pdf",
        headers=ctx["cashier1_headers"],
    )
    assert res_pdf.status_code == 200
    assert "application/pdf" in res_pdf.headers["content-type"]
    assert res_pdf.content.startswith(b"%PDF")
    assert "attachment" in res_pdf.headers.get("content-disposition", "")
    assert ".pdf" in res_pdf.headers.get("content-disposition", "")

    # 5. HTML Mode -> Clean HTML layout without auto-print
    res_html = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=html",
        headers=ctx["cashier1_headers"],
    )
    assert res_html.status_code == 200
    assert "text/html" in res_html.headers["content-type"]
    assert "window.onload" not in res_html.text
    assert inv_num in res_html.text

    # 6. JSON Mode -> Structured JSON response
    res_json = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=json",
        headers=ctx["cashier1_headers"],
    )
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["success"] is True
    assert data["invoice_id"] == inv_id
    assert data["invoice_number"] == inv_num
    assert "text_payload" in data
    assert "html" in data

    # 7. Text Mode -> Raw ESC/POS text stream
    res_text = client.get(
        f"/api/v1/invoices/{inv_id}/thermal?mode=text",
        headers=ctx["cashier1_headers"],
    )
    assert res_text.status_code == 200
    assert "text/plain" in res_text.headers["content-type"]
    assert inv_num in res_text.text


def test_invoice_reprint_modes(invoice_test_fixture):
    ctx = invoice_test_fixture

    # Create an invoice
    inv_res = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store1_id"],
            "same_state": True,
            "items": [{"product_id": ctx["product_id"], "quantity": 1, "unit_price": "100.00"}],
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
        },
    )
    assert inv_res.status_code == 201
    inv_id = inv_res.json()["id"]

    # Reprint with mode=preview -> Returns PNG image with reprint header
    res_prev = client.post(
        f"/api/v1/invoices/{inv_id}/reprint?mode=preview",
        headers=ctx["cashier1_headers"],
    )
    assert res_prev.status_code == 200
    assert "image/png" in res_prev.headers["content-type"]
    assert res_prev.content.startswith(b"\x89PNG\r\n\x1a\n")

    # Reprint with mode=view -> Returns HTML with auto-print & reprint badge
    res_view = client.post(
        f"/api/v1/invoices/{inv_id}/reprint?mode=view",
        headers=ctx["cashier1_headers"],
    )
    assert res_view.status_code == 200
    assert "text/html" in res_view.headers["content-type"]
    assert "*** DUPLICATE / REPRINT ***" in res_view.text
    assert "window.print()" in res_view.text

    # Reprint default (no mode) -> Backwards compatible JSON
    res_def = client.post(
        f"/api/v1/invoices/{inv_id}/reprint",
        headers=ctx["cashier1_headers"],
        json={"printer_type": "generic"},
    )
    assert res_def.status_code == 200
    data = res_def.json()
    assert "invoice" in data
    assert "print_payload" in data
    assert "*** DUPLICATE / REPRINT ***" in data["print_payload"]["payload"]
