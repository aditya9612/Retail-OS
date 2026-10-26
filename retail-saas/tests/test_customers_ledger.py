from datetime import date, timedelta
from decimal import Decimal
import random
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_setup_factory():
    def _create(prefix: str):
        email = f"{prefix}-owner@example.com"
        reg = client.post(
            "/api/v1/auth/register",
            params={
                "tenant_name": f"{prefix.capitalize()} Store",
                "slug": prefix,
                "email": email,
                "admin_name": f"{prefix.capitalize()} Admin",
                "password": "Password123!",
            },
        )
        assert reg.status_code == 200, reg.text

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        data = login.json()
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        user_me = client.get("/api/v1/users/me", headers=headers).json()
        return headers, user_me

    return _create


@pytest.fixture
def tenant_a(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"t-a-led-{unique_slug}")
    return headers, user


@pytest.fixture
def tenant_b(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"t-b-led-{unique_slug}")
    return headers, user


def random_phone():
    return f"9{random.randint(100000000, 999999999)}"


def random_email(prefix="cust"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def test_customer_credit_limit_lifecycle(tenant_a):
    headers, _ = tenant_a

    # 1. Create a customer
    res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Ramesh Gupta",
            "phone": random_phone(),
            "email": random_email("ramesh"),
        },
    )
    assert res.status_code == 201
    customer = res.json()
    customer_id = customer["id"]
    assert float(customer.get("credit_limit", 0)) == 0.0
    assert float(customer.get("outstanding_balance", 0)) == 0.0

    # 2. Update credit limit to 50,000.00
    patch_res = client.patch(
        f"/api/v1/customers/{customer_id}/credit-limit",
        headers=headers,
        json={"credit_limit": 50000.00},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert float(updated["credit_limit"]) == 50000.00

    # 3. Validation: negative credit limit must be rejected with 422
    neg_res = client.patch(
        f"/api/v1/customers/{customer_id}/credit-limit",
        headers=headers,
        json={"credit_limit": -100.00},
    )
    assert neg_res.status_code == 422

    # 4. Verify fetch customer reflects updated credit limit
    get_res = client.get(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert float(get_res.json()["credit_limit"]) == 50000.00


def test_customer_payment_and_ledger_statement(tenant_a):
    headers, _ = tenant_a

    # Create customer
    c_res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Suresh Patil",
            "phone": random_phone(),
            "email": random_email("suresh"),
            "credit_limit": 25000.00,
        },
    )
    assert c_res.status_code == 201
    customer_id = c_res.json()["id"]

    # Check empty initial ledger
    ledger_init = client.get(
        f"/api/v1/customers/{customer_id}/ledger",
        headers=headers,
    )
    assert ledger_init.status_code == 200
    data_init = ledger_init.json()
    assert data_init["success"] is True
    assert data_init["customer_id"] == customer_id
    assert len(data_init["entries"]) == 0
    assert float(data_init["outstanding_balance"]) == 0.0
    assert float(data_init["total_credit"]) == 0.0

    # 1. Record payment 1
    p1_res = client.post(
        f"/api/v1/customers/{customer_id}/ledger/payment",
        headers=headers,
        json={
            "amount": 1500.00,
            "payment_method": "upi",
            "reference_no": f"UPI-{uuid.uuid4().hex[:6].upper()}",
            "notes": "Partial dues payment",
        },
    )
    assert p1_res.status_code == 201
    p1 = p1_res.json()
    assert p1["entry_type"] == "CREDIT"
    assert float(p1["amount"]) == 1500.00
    assert float(p1["balance_after"]) == -1500.00

    # 2. Record payment 2
    p2_res = client.post(
        f"/api/v1/customers/{customer_id}/ledger/payment",
        headers=headers,
        json={
            "amount": 2000.00,
            "payment_method": "cash",
            "reference_no": f"CASH-{uuid.uuid4().hex[:6].upper()}",
            "notes": "Cash settlement",
        },
    )
    assert p2_res.status_code == 201
    p2 = p2_res.json()
    assert float(p2["balance_after"]) == -3500.00

    # 3. Check updated ledger statement
    ledger_full = client.get(
        f"/api/v1/customers/{customer_id}/ledger",
        headers=headers,
    )
    assert ledger_full.status_code == 200
    statement = ledger_full.json()
    assert statement["success"] is True
    assert float(statement["outstanding_balance"]) == -3500.00
    assert float(statement["total_credit"]) == 3500.00
    assert len(statement["entries"]) == 2

    # 4. Check date filtering on ledger
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    filtered_res = client.get(
        f"/api/v1/customers/{customer_id}/ledger?from_date={yesterday}&to_date={tomorrow}",
        headers=headers,
    )
    assert filtered_res.status_code == 200
    assert len(filtered_res.json()["entries"]) == 2


def test_customer_feedback_analytics(tenant_a):
    headers, _ = tenant_a

    # Check analytics with zero feedback
    empty_res = client.get(
        "/api/v1/customers/feedback/analytics",
        headers=headers,
    )
    assert empty_res.status_code == 200
    empty_data = empty_res.json()
    assert empty_data["success"] is True
    assert empty_data["total_feedbacks"] == 0
    assert empty_data["average_rating"] == 0.0

    # Create customer
    c_res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Anil Deshmukh",
            "phone": random_phone(),
            "email": random_email("anil"),
        },
    )
    customer_id = c_res.json()["id"]

    # Submit 3 feedbacks: 5 stars, 4 stars, 1 star
    for rating in [5, 4, 1]:
        f_res = client.post(
            "/api/v1/customers/feedback",
            headers=headers,
            json={
                "customer_id": customer_id,
                "rating": rating,
                "comments": f"Rating {rating} test review",
            },
        )
        assert f_res.status_code == 201

    # Check analytics
    analytics_res = client.get(
        "/api/v1/customers/feedback/analytics",
        headers=headers,
    )
    assert analytics_res.status_code == 200
    analytics = analytics_res.json()
    assert analytics["success"] is True
    assert analytics["total_feedbacks"] == 3
    # Average: (5 + 4 + 1) / 3 = 3.33
    assert analytics["average_rating"] == 3.33
    assert analytics["rating_breakdown"]["5"] == 1
    assert analytics["rating_breakdown"]["4"] == 1
    assert analytics["rating_breakdown"]["1"] == 1
    assert analytics["rating_breakdown"]["2"] == 0
    assert analytics["rating_breakdown"]["3"] == 0
    # Promoters: 2 (5 and 4), Detractors: 1 (1). NPS: (2 - 1) / 3 * 100 = 33.33%
    assert analytics["nps_score"] == 33.33


def test_customer_soft_delete(tenant_a):
    headers, _ = tenant_a

    # Create customer
    c_res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Kavita Verma",
            "phone": random_phone(),
            "email": random_email("kavita"),
        },
    )
    assert c_res.status_code == 201
    customer_id = c_res.json()["id"]

    # Delete customer
    del_res = client.delete(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
    )
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["success"] is True
    assert del_data["customer_id"] == customer_id

    # Verify status is inactive
    get_res = client.get(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "inactive"


def test_cross_tenant_isolation_on_ledger_and_delete(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    # Tenant A creates customer
    c_res = client.post(
        "/api/v1/customers",
        headers=headers_a,
        json={
            "name": "Private Customer A",
            "phone": random_phone(),
            "email": random_email("priv_a"),
        },
    )
    customer_id = c_res.json()["id"]

    # Tenant B tries to view ledger -> 404
    ledger_b = client.get(
        f"/api/v1/customers/{customer_id}/ledger",
        headers=headers_b,
    )
    assert ledger_b.status_code == 404

    # Tenant B tries to record payment -> 404
    pay_b = client.post(
        f"/api/v1/customers/{customer_id}/ledger/payment",
        headers=headers_b,
        json={"amount": 100.00},
    )
    assert pay_b.status_code == 404

    # Tenant B tries to update credit limit -> 404
    cl_b = client.patch(
        f"/api/v1/customers/{customer_id}/credit-limit",
        headers=headers_b,
        json={"credit_limit": 99999.00},
    )
    assert cl_b.status_code == 404

    # Tenant B tries to delete customer -> 404
    del_b = client.delete(
        f"/api/v1/customers/{customer_id}",
        headers=headers_b,
    )
    assert del_b.status_code == 404


def test_customer_ledger_pdf_export_and_send(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    # 1. Create Customer
    c_res = client.post(
        "/api/v1/customers",
        headers=headers_a,
        json={
            "name": "Vikas Shinde",
            "phone": random_phone(),
            "email": random_email("vikas"),
            "credit_limit": 15000.00,
        },
    )
    assert c_res.status_code == 201
    customer_id = c_res.json()["id"]

    # 2. Add Payment to ledger
    pay_res = client.post(
        f"/api/v1/customers/{customer_id}/ledger/payment",
        headers=headers_a,
        json={
            "amount": 2500.00,
            "payment_method": "upi",
            "reference_no": "UPI-KHATA-001",
            "notes": "Advance payment for account",
        },
    )
    assert pay_res.status_code == 201

    # 3. Export Ledger PDF
    pdf_res = client.get(
        f"/api/v1/customers/{customer_id}/ledger/pdf",
        headers=headers_a,
    )
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert pdf_res.content.startswith(b"%PDF")

    # 4. Send Ledger PDF via WhatsApp
    send_res = client.post(
        f"/api/v1/customers/{customer_id}/send-ledger-pdf?channel=WHATSAPP",
        headers=headers_a,
    )
    assert send_res.status_code == 200
    send_data = send_res.json()
    assert send_data["success"] is True
    assert send_data["customer_id"] == customer_id
    assert send_data["communication_id"] > 0
    assert "WHATSAPP" in send_data["message"]

    # 5. Verify communication history recorded
    wa_history = client.get(
        "/api/v1/customers/notifications/whatsapp",
        headers=headers_a,
    )
    assert wa_history.status_code == 200
    wa_list = wa_history.json()["data"]
    assert len(wa_list) >= 1
    matched = any("Ledger PDF" in m.get("message", "") for m in wa_list)
    assert matched is True

    # 6. Tenant B cannot access PDF or send PDF for Tenant A's customer
    assert client.get(f"/api/v1/customers/{customer_id}/ledger/pdf", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/customers/{customer_id}/send-ledger-pdf", headers=headers_b).status_code == 404


def test_customer_outstanding_balance_deactivation_protection(tenant_a):
    headers, _ = tenant_a

    # Create customer
    c_res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Dues Protection Cust",
            "phone": random_phone(),
            "email": random_email("dues"),
            "credit_limit": 2000.00,
        },
    )
    assert c_res.status_code == 201
    customer_id = c_res.json()["id"]

    # Directly set outstanding dues
    from app.core.database import SessionLocal
    from app.models.customer import Customer
    db = SessionLocal()
    try:
        cust = db.query(Customer).filter(Customer.id == customer_id).first()
        cust.outstanding_balance = Decimal("450.00")
        db.commit()
    finally:
        db.close()

    # Attempt deletion -> must fail with 400
    del_res = client.delete(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
    )
    assert del_res.status_code == 400
    assert "Cannot deactivate customer with outstanding dues" in str(del_res.json())

    # Attempt status patch to inactive -> must fail with 400
    patch_res = client.patch(
        f"/api/v1/customers/{customer_id}/status",
        headers=headers,
        json={"status": "inactive"},
    )
    assert patch_res.status_code == 400
    assert "Cannot deactivate customer with outstanding dues" in str(patch_res.json())

    # Settle dues via customer payment
    pay_res = client.post(
        f"/api/v1/customers/{customer_id}/ledger/payment",
        headers=headers,
        json={
            "amount": 450.00,
            "payment_method": "CASH",
            "reference_no": "PAY-SETTLE-001",
        },
    )
    assert pay_res.status_code == 201
    assert Decimal(str(pay_res.json()["balance_after"])) == Decimal("0.00")

    # Now deactivation succeeds
    del_success = client.delete(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
    )
    assert del_success.status_code == 200
    assert del_success.json()["success"] is True


def test_dnd_opt_out_compliance(tenant_a):
    headers, _ = tenant_a

    # Create customer with DND enabled (opt-in = False)
    c_res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "DND Compliant User",
            "phone": random_phone(),
            "email": random_email("dnd"),
            "sms_opt_in": False,
            "whatsapp_opt_in": False,
        },
    )
    assert c_res.status_code == 201
    customer_id = c_res.json()["id"]

    # 1. Direct SMS should be blocked
    sms_res = client.post(
        "/api/v1/customers/notifications/sms",
        headers=headers,
        json={
            "customer_id": customer_id,
            "communication_type": "SMS",
            "message": "Special Promo Offer",
        },
    )
    assert sms_res.status_code == 400
    assert "Customer has opted out of SMS communications" in str(sms_res.json())

    # 2. Direct WhatsApp should be blocked
    wa_res = client.post(
        "/api/v1/customers/notifications/whatsapp",
        headers=headers,
        json={
            "customer_id": customer_id,
            "communication_type": "WHATSAPP",
            "message": "Order tracking update",
        },
    )
    assert wa_res.status_code == 400
    assert "Customer has opted out of WhatsApp communications" in str(wa_res.json())

    # 3. Campaign should exclude opted-out customers into failed_count
    # Create another customer with opt-in True
    c_optin_res = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Opted In User",
            "phone": random_phone(),
            "email": random_email("optin"),
            "sms_opt_in": True,
        },
    )
    assert c_optin_res.status_code == 201
    optin_id = c_optin_res.json()["id"]

    camp_res = client.post(
        "/api/v1/customers/campaigns/send",
        headers=headers,
        json={
            "customer_ids": [customer_id, optin_id],
            "communication_type": "SMS",
            "message": "Diwali mega sale!",
        },
    )
    assert camp_res.status_code == 200
    camp_data = camp_res.json()
    assert camp_data["sent_count"] == 1
    assert camp_data["failed_count"] == 1
    assert camp_data["total_customers"] == 2


def test_referral_code_custom_and_auto_generation(tenant_a):
    headers, _ = tenant_a

    c1 = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Referrer One", "phone": random_phone(), "email": random_email("ref1")},
    ).json()

    c2 = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Referral Two", "phone": random_phone(), "email": random_email("ref2")},
    ).json()

    # Auto generation when referral_code omitted
    ref_auto = client.post(
        "/api/v1/customers/referrals",
        headers=headers,
        json={"customer_id": c1["id"], "referred_customer_id": c2["id"]},
    )
    assert ref_auto.status_code == 200
    auto_code = ref_auto.json()["referral_code"]
    assert auto_code.startswith("REF-")

    # Custom referral code
    c3 = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Referrer Three", "phone": random_phone(), "email": random_email("ref3")},
    ).json()

    custom_code = f"VIP-{uuid.uuid4().hex[:6].upper()}"
    ref_custom = client.post(
        "/api/v1/customers/referrals",
        headers=headers,
        json={"customer_id": c3["id"], "referral_code": custom_code},
    )
    assert ref_custom.status_code == 200
    assert ref_custom.json()["referral_code"] == custom_code


def test_birthday_and_subresource_pagination_analytics(tenant_a):
    headers, _ = tenant_a

    # Create customer with specific birthday (e.g. 1995-11-20)
    c = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "November Baby",
            "phone": random_phone(),
            "email": random_email("nov"),
            "birthday": "1995-11-20",
        },
    ).json()

    # Query birthdays with month=11 and day=20
    b_res = client.get(
        "/api/v1/customers/birthdays?month=11&day=20",
        headers=headers,
    )
    assert b_res.status_code == 200
    b_list = b_res.json()
    assert any(cust["id"] == c["id"] for cust in b_list)

    # Sub-resource pagination check
    fb_res = client.get(
        "/api/v1/customers/feedback?page=1&page_size=5",
        headers=headers,
    )
    assert fb_res.status_code == 200

    # Analytics date range check
    analytics_res = client.get(
        "/api/v1/customers/feedback/analytics?from_date=2026-01-01&to_date=2026-12-31",
        headers=headers,
    )
    assert analytics_res.status_code == 200
    assert "average_rating" in analytics_res.json()
