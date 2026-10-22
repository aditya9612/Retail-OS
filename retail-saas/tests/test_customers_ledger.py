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
