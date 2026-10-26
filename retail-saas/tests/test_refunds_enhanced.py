import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app

client = TestClient(app)


@pytest.fixture
def refunds_setup():
    suffix = uuid.uuid4().hex[:8]
    email = f"ref-admin-{suffix}@testcorp.com"
    slug = f"ref-tenant-{suffix}"
    password = "TestPassword123!"

    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Refund Tenant {suffix}",
            "slug": slug,
            "email": email,
            "admin_name": "Refund Admin",
            "password": password,
        },
    )
    assert reg.status_code == 200, reg.text
    tenant_id = reg.json()["tenant_id"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": f"Store {suffix}", "code": f"ST-{suffix[:4]}"},
        headers=headers,
    ).json()

    product = client.post(
        "/api/v1/products",
        json={
            "name": "Test Product",
            "sku": f"SKU-{suffix}",
            "price": "100.00",
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

    customer_resp = client.post(
        "/api/v1/customers",
        json={
            "name": "Johnathan Doe",
            "phone": f"9{uuid.uuid4().int % 1000000000:09d}",
            "email": f"john-{suffix}@example.com",
        },
        headers=headers,
    )
    assert customer_resp.status_code == 201, customer_resp.text
    customer = customer_resp.json()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store": store,
        "product": product,
        "customer": customer,
    }


def _create_invoice(setup_data, with_customer=True, amount="118.00"):
    headers = setup_data["headers"]
    store_id = setup_data["store"]["id"]
    customer_id = setup_data["customer"]["id"] if with_customer else None

    # Add item to cart
    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id},
        json={"product_id": setup_data["product"]["id"], "quantity": "1"},
        headers=headers,
    )

    invoice_payload = {
        "store_id": store_id,
        "customer_id": customer_id,
        "payments": [{"payment_mode": "cash", "amount": amount}],
    }

    inv_resp = client.post("/api/v1/invoices", json=invoice_payload, headers=headers)
    assert inv_resp.status_code == 201, inv_resp.text
    return inv_resp.json()


def test_store_credit_refund_credits_customer_wallet(refunds_setup):
    headers = refunds_setup["headers"]
    customer_id = refunds_setup["customer"]["id"]
    invoice = _create_invoice(refunds_setup, with_customer=True, amount="118.00")

    # 1. Check initial customer wallet
    wallet_resp = client.get(f"/api/v1/customers/wallet/{customer_id}", headers=headers)
    initial_balance = Decimal(str(wallet_resp.json()["current_balance"])) if wallet_resp.status_code == 200 else Decimal("0.00")

    # 2. Create store_credit refund
    create_resp = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "50.00",
            "refund_method": "store_credit",
            "reason": "Return for store credit voucher",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    refund = create_resp.json()
    assert refund["status"] == "pending"
    assert refund["refund_method"] == "store_credit"
    assert refund["invoice_number"] == invoice["invoice_number"]

    # 3. Approve refund
    appr_resp = client.post(f"/api/v1/refunds/{refund['id']}/approve", headers=headers)
    assert appr_resp.status_code == 200, appr_resp.text
    approved_refund = appr_resp.json()
    assert approved_refund["status"] == "approved"
    assert approved_refund["credit_note_id"] is not None
    assert approved_refund["credit_note_no"].startswith("CN-")

    # 4. Verify customer wallet was credited by 50.00
    wallet_after = client.get(f"/api/v1/customers/wallet/{customer_id}", headers=headers)
    assert wallet_after.status_code == 200
    new_balance = Decimal(str(wallet_after.json()["current_balance"]))
    assert new_balance == initial_balance + Decimal("50.00")


def test_store_credit_refund_without_customer_rejected(refunds_setup):
    headers = refunds_setup["headers"]
    invoice = _create_invoice(refunds_setup, with_customer=False, amount="118.00")

    # Attempt store_credit refund on invoice with no registered customer
    create_resp = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "50.00",
            "refund_method": "store_credit",
            "reason": "Anonymous store credit attempt",
        },
        headers=headers,
    )
    assert create_resp.status_code == 400
    assert "Store credit refund requires a registered customer" in create_resp.text


def test_reject_refund_with_reason(refunds_setup):
    headers = refunds_setup["headers"]
    invoice = _create_invoice(refunds_setup, with_customer=True, amount="118.00")

    create_resp = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "30.00",
            "refund_method": "cash",
            "reason": "Damaged box",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    refund_id = create_resp.json()["id"]

    # Reject with custom reason
    rej_resp = client.post(
        f"/api/v1/refunds/{refund_id}/reject",
        json={"reason": "Goods tampered after purchase"},
        headers=headers,
    )
    assert rej_resp.status_code == 200, rej_resp.text
    rejected = rej_resp.json()
    assert rejected["status"] == "rejected"
    assert "Rejected: Goods tampered after purchase" in rejected["reason"]


def test_list_refunds_filtering_and_pending_approval(refunds_setup):
    headers = refunds_setup["headers"]
    invoice = _create_invoice(refunds_setup, with_customer=True, amount="118.00")

    # Create 2 refunds: 1 pending, 1 approved
    r1 = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "20.00",
            "refund_method": "cash",
            "reason": "Minor defect",
        },
        headers=headers,
    ).json()

    r2 = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "25.00",
            "refund_method": "cash",
            "reason": "Defect 2",
        },
        headers=headers,
    ).json()

    # Approve r2
    client.post(f"/api/v1/refunds/{r2['id']}/approve", headers=headers)

    # 1. Filter by status: pending
    pending_list = client.get("/api/v1/refunds", params={"status": "pending"}, headers=headers).json()
    assert any(r["id"] == r1["id"] for r in pending_list)
    assert not any(r["id"] == r2["id"] for r in pending_list)

    # 2. Filter by status: approved
    approved_list = client.get("/api/v1/refunds", params={"status": "approved"}, headers=headers).json()
    assert any(r["id"] == r2["id"] for r in approved_list)
    assert not any(r["id"] == r1["id"] for r in approved_list)

    # 3. Manager pending-approval queue endpoint
    queue_resp = client.get("/api/v1/refunds/pending-approval", headers=headers)
    assert queue_resp.status_code == 200
    queue = queue_resp.json()
    assert any(r["id"] == r1["id"] for r in queue)
    assert all(r["status"] == "pending" for r in queue)


def test_refund_receipt_voucher_and_pdf(refunds_setup):
    headers = refunds_setup["headers"]
    invoice = _create_invoice(refunds_setup, with_customer=True, amount="118.00")

    ref = client.post(
        "/api/v1/refunds",
        json={
            "invoice_id": invoice["id"],
            "refund_amount": "40.00",
            "refund_method": "cash",
            "reason": "Customer exchange cash diff",
        },
        headers=headers,
    ).json()

    # Receipt before approval -> rejected
    receipt_early = client.get(f"/api/v1/refunds/{ref['id']}/receipt/pdf", headers=headers)
    assert receipt_early.status_code == 400

    # Approve refund
    client.post(f"/api/v1/refunds/{ref['id']}/approve", headers=headers)

    # 1. JSON receipt voucher with thermal slip text (default without mode or mode=json)
    receipt_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=json", headers=headers)
    assert receipt_resp.status_code == 200, receipt_resp.text
    receipt_data = receipt_resp.json()
    assert receipt_data["refund_id"] == ref["id"]
    assert receipt_data["invoice_number"] == invoice["invoice_number"]
    assert "REFUND PAYMENT VOUCHER" in receipt_data["thermal_text"]
    assert "Rs. 40.00" in receipt_data["thermal_text"]

    # 1b. Mode preview -> 80mm PNG thermal image
    preview_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=preview", headers=headers)
    assert preview_resp.status_code == 200
    assert "image/png" in preview_resp.headers["content-type"]
    assert preview_resp.content.startswith(b"\x89PNG")

    # 1c. Mode view -> HTML with auto-print
    view_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=view", headers=headers)
    assert view_resp.status_code == 200
    assert "text/html" in view_resp.headers["content-type"]
    assert "window.print()" in view_resp.text
    assert "REFUND PAYMENT VOUCHER" in view_resp.text

    # 1d. Mode download -> text file attachment
    dl_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=download", headers=headers)
    assert dl_resp.status_code == 200
    assert "text/plain" in dl_resp.headers["content-type"]
    assert "attachment" in dl_resp.headers["content-disposition"]
    assert "REFUND PAYMENT VOUCHER" in dl_resp.text

    # 1e. Mode pdf -> 80mm thermal PDF
    thermal_pdf_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=pdf", headers=headers)
    assert thermal_pdf_resp.status_code == 200
    assert "application/pdf" in thermal_pdf_resp.headers["content-type"]
    assert thermal_pdf_resp.content.startswith(b"%PDF")

    # 1f. Mode html -> styled raw HTML
    html_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=html", headers=headers)
    assert html_resp.status_code == 200
    assert "text/html" in html_resp.headers["content-type"]

    # 1g. Mode text -> raw ESC/POS stream
    txt_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt?mode=text", headers=headers)
    assert txt_resp.status_code == 200
    assert "text/plain" in txt_resp.headers["content-type"]

    # 2. PDF receipt download (mode=download and mode=preview)
    pdf_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt/pdf?mode=download", headers=headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf_resp.headers["content-disposition"]
    assert pdf_resp.content.startswith(b"%PDF")

    pdf_prev_resp = client.get(f"/api/v1/refunds/{ref['id']}/receipt/pdf?mode=preview", headers=headers)
    assert pdf_prev_resp.status_code == 200
    assert "inline" in pdf_prev_resp.headers["content-disposition"]

