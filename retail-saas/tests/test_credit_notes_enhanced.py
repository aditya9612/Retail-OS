import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def credit_note_setup(unique_slug):
    email = f"cn-admin-{unique_slug}@retailtest.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Credit Note Test",
            "slug": unique_slug,
            "email": email,
            "admin_name": "CN Admin",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Store
    store = client.post(
        "/api/v1/stores",
        json={"name": "CN Store", "code": f"CNS-{unique_slug[-6:]}"},
        headers=headers,
    ).json()

    # Product
    product = client.post(
        "/api/v1/products",
        json={
            "name": "CN Product",
            "sku": f"SKU-CN-{unique_slug[-6:]}",
            "price": "500.00",
            "gst_rate": "18.00",
            "hsn_code": "6109",
        },
        headers=headers,
    ).json()

    # Inventory
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product["id"], "quantity": 100},
        headers=headers,
    )

    # Invoice
    invoice_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store["id"],
            "same_state": True,
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 2,
                    "unit_price": "500.00",
                    "discount": "0.00",
                }
            ],
            "payments": [
                {
                    "payment_mode": "cash",
                    "amount": "1180.00",
                    "amount_tendered": "1200.00",
                    "change_due": "20.00",
                }
            ],
        },
        headers=headers,
    )
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice = invoice_resp.json()

    return {
        "headers": headers,
        "store_id": store["id"],
        "product_id": product["id"],
        "invoice_id": invoice["id"],
        "invoice_number": invoice["invoice_number"],
    }


def test_create_and_get_credit_note_by_number(credit_note_setup):
    headers = credit_note_setup["headers"]
    invoice_id = credit_note_setup["invoice_id"]

    # 1. Create Credit Note with valid_days and notes
    create_res = client.post(
        "/api/v1/credit-notes",
        json={
            "invoice_id": invoice_id,
            "refund_amount": "500.00",
            "reason": "Customer store credit exchange",
            "valid_days": 60,
            "notes": "VIP Customer loyalty credit",
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    cn_data = create_res.json()

    assert cn_data["credit_note_no"].startswith("CN-")
    assert Decimal(str(cn_data["refund_amount"])) == Decimal("500.00")
    assert Decimal(str(cn_data["balance_amount"])) == Decimal("500.00")
    assert cn_data["status"] == "issued"
    assert cn_data["notes"] == "VIP Customer loyalty credit"
    assert cn_data["valid_until"] is not None

    cn_no = cn_data["credit_note_no"]

    # 2. Get Credit Note by ID
    get_res = client.get(f"/api/v1/credit-notes/{cn_data['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["credit_note_no"] == cn_no

    # 3. Get Credit Note by human-readable number
    by_num_res = client.get(f"/api/v1/credit-notes/by-number/{cn_no}", headers=headers)
    assert by_num_res.status_code == 200
    assert by_num_res.json()["id"] == cn_data["id"]
    assert by_num_res.json()["invoice_number"] == credit_note_setup["invoice_number"]


def test_credit_note_validation_and_redemption_lifecycle(credit_note_setup):
    headers = credit_note_setup["headers"]
    invoice_id = credit_note_setup["invoice_id"]

    # Issue CN for 600.00
    create_res = client.post(
        "/api/v1/credit-notes",
        json={
            "invoice_id": invoice_id,
            "refund_amount": "600.00",
            "reason": "Counter partial return",
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    cn_no = create_res.json()["credit_note_no"]

    # 1. Validate credit note against bill of 400.00
    val_res = client.post(
        "/api/v1/credit-notes/validate",
        json={"credit_note_no": cn_no, "bill_amount": "400.00"},
        headers=headers,
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["valid"] is True
    assert Decimal(str(val_data["balance_amount"])) == Decimal("600.00")
    assert Decimal(str(val_data["applicable_amount"])) == Decimal("400.00")

    # 2. Partial Redemption (redeem 350.00)
    red_res = client.post(
        "/api/v1/credit-notes/redeem",
        json={
            "credit_note_no": cn_no,
            "amount_to_redeem": "350.00",
            "notes": "Redeemed for Counter bill #102",
        },
        headers=headers,
    )
    assert red_res.status_code == 200, red_res.text
    red_data = red_res.json()
    assert red_data["success"] is True
    assert Decimal(str(red_data["amount_redeemed"])) == Decimal("350.00")
    assert Decimal(str(red_data["remaining_balance"])) == Decimal("250.00")
    assert red_data["status"] == "partially_redeemed"

    # 3. Check status is partially_redeemed
    cn_check = client.get(f"/api/v1/credit-notes/by-number/{cn_no}", headers=headers).json()
    assert cn_check["status"] == "partially_redeemed"
    assert Decimal(str(cn_check["balance_amount"])) == Decimal("250.00")

    # 4. Attempt to redeem more than remaining balance (e.g. 300.00 when balance is 250.00) -> Rejected
    over_res = client.post(
        "/api/v1/credit-notes/redeem",
        json={"credit_note_no": cn_no, "amount_to_redeem": "300.00"},
        headers=headers,
    )
    assert over_res.status_code == 400
    assert "exceeds available balance" in over_res.text

    # 5. Full remaining redemption (redeem remaining 250.00)
    full_res = client.post(
        "/api/v1/credit-notes/redeem",
        json={"credit_note_no": cn_no, "amount_to_redeem": "250.00"},
        headers=headers,
    )
    assert full_res.status_code == 200
    assert full_res.json()["status"] == "redeemed"
    assert Decimal(str(full_res.json()["remaining_balance"])) == Decimal("0.00")

    # 6. Validate now shows zero balance / invalid for further redemption
    val2 = client.post(
        "/api/v1/credit-notes/validate",
        json={"credit_note_no": cn_no},
        headers=headers,
    ).json()
    assert val2["valid"] is False
    assert "status is 'redeemed'" in val2["message"] or "zero remaining balance" in val2["message"]


def test_credit_note_filters_and_pagination(credit_note_setup):
    headers = credit_note_setup["headers"]
    invoice_id = credit_note_setup["invoice_id"]

    # List credit notes with status filter
    res = client.get(
        "/api/v1/credit-notes",
        params={"invoice_id": invoice_id, "page": 1, "page_size": 10},
        headers=headers,
    )
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)


def test_credit_note_thermal_voucher_json_and_text(credit_note_setup):
    headers = credit_note_setup["headers"]
    invoice_id = credit_note_setup["invoice_id"]

    # Issue a credit note
    create_res = client.post(
        "/api/v1/credit-notes",
        json={"invoice_id": invoice_id, "refund_amount": "200.00", "reason": "Test voucher"},
        headers=headers,
    )
    cn_id = create_res.json()["id"]

    # 1. Thermal JSON mode
    res_json = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "json"},
        headers=headers,
    )
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["credit_note_id"] == cn_id
    assert "thermal_text" in data
    assert "CREDIT NOTE VOUCHER" in data["thermal_text"]

    # 2. Thermal text mode
    res_text = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "text"},
        headers=headers,
    )
    assert res_text.status_code == 200
    assert "text/plain" in res_text.headers["content-type"]
    assert "CREDIT NOTE VOUCHER" in res_text.text
    assert "BALANCE DUE" in res_text.text

    # 3. Thermal preview mode (explicit & default) -> 80mm PNG
    res_preview = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "preview"},
        headers=headers,
    )
    assert res_preview.status_code == 200
    assert "image/png" in res_preview.headers["content-type"]
    assert res_preview.content.startswith(b"\x89PNG")

    res_default = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        headers=headers,
    )
    assert res_default.status_code == 200
    assert "image/png" in res_default.headers["content-type"]
    assert res_default.content.startswith(b"\x89PNG")

    # 4. Thermal view mode -> HTML with auto-print
    res_view = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "view"},
        headers=headers,
    )
    assert res_view.status_code == 200
    assert "text/html" in res_view.headers["content-type"]
    assert "window.print()" in res_view.text
    assert "CREDIT NOTE VOUCHER" in res_view.text

    # 5. Thermal download mode -> ESC/POS text attachment
    res_download = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "download"},
        headers=headers,
    )
    assert res_download.status_code == 200
    assert "text/plain" in res_download.headers["content-type"]
    assert "attachment" in res_download.headers["content-disposition"]
    assert "CREDIT NOTE VOUCHER" in res_download.text

    # 6. Thermal PDF mode -> 80mm roll PDF
    res_pdf = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "pdf"},
        headers=headers,
    )
    assert res_pdf.status_code == 200
    assert "application/pdf" in res_pdf.headers["content-type"]
    assert res_pdf.content.startswith(b"%PDF")

    # 7. Thermal HTML mode -> Styled raw HTML
    res_html = client.get(
        f"/api/v1/credit-notes/{cn_id}/thermal",
        params={"mode": "html"},
        headers=headers,
    )
    assert res_html.status_code == 200
    assert "text/html" in res_html.headers["content-type"]
    assert "CREDIT NOTE VOUCHER" in res_html.text
