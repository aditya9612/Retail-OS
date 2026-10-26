import uuid
from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def payment_setup(unique_slug):
    email = f"pay-admin-{unique_slug}@retailtest.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Payment Test",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Payment Admin",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Store
    rnd_suffix = unique_slug.replace("-", "")[-6:].upper()
    store = client.post(
        "/api/v1/stores",
        json={"name": "Payment Store", "code": f"PST-{rnd_suffix}"},
        headers=headers,
    ).json()

    # Product
    product = client.post(
        "/api/v1/products",
        json={
            "name": "Payment Item",
            "sku": f"SKU-PAY-{rnd_suffix}",
            "price": "500.00",
            "gst_rate": "18.00",
            "hsn_code": "6109",
        },
        headers=headers,
    ).json()

    # Stock
    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product["id"], "quantity": 100},
        headers=headers,
    )

    # Create Invoice & Order
    inv_res = client.post(
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
    assert inv_res.status_code == 201, inv_res.text
    order_id = inv_res.json()["order_id"]

    return {
        "headers": headers,
        "store_id": store["id"],
        "order_id": order_id,
        "unique_slug": unique_slug,
    }


def test_payment_gateways_crud_and_duplicate_prevention(payment_setup):
    headers = payment_setup["headers"]
    slug = payment_setup["unique_slug"][-4:]

    # 1. Create Payment Gateway
    gw_payload = {
        "gateway_name": f"Razorpay Test {slug}",
        "merchant_id": f"rzp_live_{slug}123",
        "api_key": f"key_{slug}abc",
        "secret_key": f"sec_{slug}xyz",
        "environment": "LIVE",
        "status": "ACTIVE",
    }
    create_res = client.post(
        "/api/v1/payments/payment-gateways",
        json=gw_payload,
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    gw_data = create_res.json()
    assert gw_data["gateway_name"] == f"Razorpay Test {slug}"
    assert gw_data["status"] == "ACTIVE"
    gw_id = gw_data["id"]

    # 2. Duplicate gateway_name prevention
    dup_name_res = client.post(
        "/api/v1/payments/payment-gateways",
        json={**gw_payload, "merchant_id": f"rzp_diff_{slug}999"},
        headers=headers,
    )
    assert dup_name_res.status_code == 400
    assert "Gateway name already exists" in dup_name_res.text

    # 3. Duplicate merchant_id prevention
    dup_m_res = client.post(
        "/api/v1/payments/payment-gateways",
        json={**gw_payload, "gateway_name": f"Other Gateway {slug}"},
        headers=headers,
    )
    assert dup_m_res.status_code == 400
    assert "Merchant ID already exists" in dup_m_res.text

    # 4. List Gateways
    list_res = client.get("/api/v1/payments/payment-gateways", headers=headers)
    assert list_res.status_code == 200
    assert any(g["id"] == gw_id for g in list_res.json())

    # 5. Get Gateway by ID
    get_res = client.get(f"/api/v1/payments/payment-gateways/{gw_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == gw_id

    # 6. Update Gateway
    update_res = client.put(
        f"/api/v1/payments/payment-gateways/{gw_id}",
        json={"gateway_name": f"Razorpay Updated {slug}", "status": "INACTIVE"},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["gateway_name"] == f"Razorpay Updated {slug}"
    assert update_res.json()["status"] == "INACTIVE"

    # 7. Safe Delete Gateway
    del_res = client.delete(f"/api/v1/payments/payment-gateways/{gw_id}", headers=headers)
    assert del_res.status_code == 200


def test_payment_splits_lifecycle_and_over_allocation(payment_setup):
    headers = payment_setup["headers"]
    order_id = payment_setup["order_id"]
    slug = payment_setup["unique_slug"][-4:]

    # Create Payment of 500.00 for order
    txn_ref = f"TXN-{slug}-901"
    pmt_res = client.post(
        "/api/v1/payments",
        json={
            "order_id": order_id,
            "payment_method": "upi",
            "amount": "500.00",
            "transaction_id": txn_ref,
        },
        headers=headers,
    )
    assert pmt_res.status_code == 201, pmt_res.text
    payment_id = pmt_res.json()["id"]

    # 1. Create first split: 200.00 cash
    split1_res = client.post(
        "/api/v1/payments/payment-splits",
        json={
            "transaction_id": payment_id,
            "payment_method": "cash",
            "amount": "200.00",
        },
        headers=headers,
    )
    assert split1_res.status_code == 201, split1_res.text
    s1_data = split1_res.json()
    assert s1_data["transaction_id"] == payment_id
    assert s1_data["payment_method"] == "cash"
    assert Decimal(str(s1_data["amount"])) == Decimal("200.00")
    split1_id = s1_data["id"]

    # 2. Duplicate payment_method rejection in same split
    dup_method = client.post(
        "/api/v1/payments/payment-splits",
        json={
            "transaction_id": payment_id,
            "payment_method": "cash",
            "amount": "50.00",
        },
        headers=headers,
    )
    assert dup_method.status_code == 400
    assert "Payment method already exists" in dup_method.text

    # 3. Create second split: 300.00 upi (total is now 200 + 300 = 500)
    split2_res = client.post(
        "/api/v1/payments/payment-splits",
        json={
            "transaction_id": payment_id,
            "payment_method": "upi",
            "amount": "300.00",
        },
        headers=headers,
    )
    assert split2_res.status_code == 201

    # 4. Over-allocation rejection (total 500 + 50 = 550 > 500)
    over_res = client.post(
        "/api/v1/payments/payment-splits",
        json={
            "transaction_id": payment_id,
            "payment_method": "card",
            "amount": "50.00",
        },
        headers=headers,
    )
    assert over_res.status_code == 400
    assert "Split payment total cannot exceed payment amount" in over_res.text

    # 5. List Splits filtered by transaction_id
    splits_by_tx = client.get(
        f"/api/v1/payments/payment-splits?transaction_id={payment_id}",
        headers=headers,
    )
    assert splits_by_tx.status_code == 200
    splits_list = splits_by_tx.json()
    assert len(splits_list) == 2

    # 6. List all payment splits
    all_splits = client.get("/api/v1/payments/payment-splits", headers=headers)
    assert all_splits.status_code == 200
    assert len(all_splits.json()) >= 2

    # 7. Get Split by ID
    get_split = client.get(f"/api/v1/payments/payment-splits/{split1_id}", headers=headers)
    assert get_split.status_code == 200
    assert get_split.json()["id"] == split1_id
    assert get_split.json()["payment_method"] == "cash"


def test_settlements_lifecycle_past_date_and_filters(payment_setup):
    headers = payment_setup["headers"]
    slug = payment_setup["unique_slug"][-4:]

    # Create Gateway
    gw = client.post(
        "/api/v1/payments/payment-gateways",
        json={
            "gateway_name": f"Settlement GW {slug}",
            "merchant_id": f"m_stl_{slug}123",
            "api_key": f"key_stl_{slug}",
            "secret_key": f"sec_stl_{slug}",
        },
        headers=headers,
    ).json()

    # 1. Create Settlement with yesterday's date (T+1 bank reconciliation)
    yesterday = date.today() - timedelta(days=1)
    ref_no = f"SETTLE-{slug}-801"
    create_stl = client.post(
        "/api/v1/payments/settlements",
        json={
            "gateway_id": gw["id"],
            "settlement_date": str(yesterday),
            "total_amount": "15000.00",
            "status": "completed",
            "reference_no": ref_no,
        },
        headers=headers,
    )
    assert create_stl.status_code == 201, create_stl.text
    stl_data = create_stl.json()
    assert stl_data["total_amount"] == 15000.0 or Decimal(str(stl_data["total_amount"])) == Decimal("15000.00")
    stl_id = stl_data["id"]

    # 2. Duplicate reference_no rejection
    dup_ref = client.post(
        "/api/v1/payments/settlements",
        json={
            "gateway_id": gw["id"],
            "settlement_date": str(yesterday),
            "total_amount": "500.00",
            "status": "pending",
            "reference_no": ref_no,
        },
        headers=headers,
    )
    assert dup_ref.status_code == 400
    assert "Settlement reference number already exists" in dup_ref.text

    # 3. List Settlements with filters
    list_stl = client.get(
        "/api/v1/payments/settlements",
        params={"gateway_id": gw["id"], "status": "completed"},
        headers=headers,
    )
    assert list_stl.status_code == 200
    assert len(list_stl.json()) >= 1

    # 4. Get Settlement by ID
    get_stl = client.get(f"/api/v1/payments/settlements/{stl_id}", headers=headers)
    assert get_stl.status_code == 200
    assert get_stl.json()["id"] == stl_id
    assert get_stl.json()["reference_no"] == ref_no


def test_webhook_logs_and_payment_verification(payment_setup):
    headers = payment_setup["headers"]
    order_id = payment_setup["order_id"]
    slug = payment_setup["unique_slug"][-4:]

    # Create Payment
    txn_ref = f"TXN-WH-{slug}-501"
    pmt = client.post(
        "/api/v1/payments",
        json={
            "order_id": order_id,
            "payment_method": "card",
            "amount": "300.00",
            "transaction_id": txn_ref,
        },
        headers=headers,
    ).json()
    payment_id = pmt["id"]

    # 1. Create Webhook Log
    create_wh = client.post(
        "/api/v1/payments/webhooks",
        json={
            "event_type": "payment.authorized",
            "transaction_id": txn_ref,
            "payload": '{"event": "payment.authorized", "id": "pay_999"}',
            "status": "received",
        },
        headers=headers,
    )
    assert create_wh.status_code == 201, create_wh.text
    wh_data = create_wh.json()
    assert wh_data["transaction_id"] == txn_ref
    wh_id = wh_data["id"]

    # 2. Duplicate webhook log rejection
    dup_wh = client.post(
        "/api/v1/payments/webhooks",
        json={
            "event_type": "payment.authorized",
            "transaction_id": txn_ref,
            "payload": '{"event": "payment.authorized"}',
            "status": "received",
        },
        headers=headers,
    )
    assert dup_wh.status_code == 400
    assert "Webhook event already exists" in dup_wh.text

    # 3. List Webhook Logs with filter
    list_wh = client.get(
        "/api/v1/payments/webhooks",
        params={"event_type": "payment.authorized"},
        headers=headers,
    )
    assert list_wh.status_code == 200
    assert any(w["id"] == wh_id for w in list_wh.json())

    # 4. Get Webhook Log by ID
    get_wh = client.get(f"/api/v1/payments/webhooks/{wh_id}", headers=headers)
    assert get_wh.status_code == 200
    assert get_wh.json()["id"] == wh_id

    # 5. Get Payment by ID
    get_pmt = client.get(f"/api/v1/payments/{payment_id}", headers=headers)
    assert get_pmt.status_code == 200
    assert get_pmt.json()["id"] == payment_id

    # 6. Verify Payment
    verify_res = client.post(
        f"/api/v1/payments/{payment_id}/verify",
        json={
            "transaction_id": txn_ref,
            "status": "completed",
            "gateway_response": "Transaction approved via POS terminal",
        },
        headers=headers,
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "completed"
