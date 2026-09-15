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
    headers, user = auth_setup_factory(f"t-a-{unique_slug}")
    return headers, user


@pytest.fixture
def tenant_b(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"t-b-{unique_slug}")
    return headers, user


def random_phone():
    return f"9{random.randint(100000000, 999999999)}"


def random_email(prefix="cust"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def create_test_customer(
    headers,
    name="Test Customer",
    phone=None,
    email=None,
    address="123 MG Road, Pune",
    birthday="1995-05-15",
):
    if phone is None:
        phone = random_phone()
    payload = {
        "name": name,
        "phone": phone,
        "address": address,
        "birthday": birthday,
    }
    if email:
        payload["email"] = email
    resp = client.post("/api/v1/customers", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_customer_valid(tenant_a):
    headers, _ = tenant_a
    phone = random_phone()
    email = random_email("rahul")
    payload = {
        "name": "Rahul Sharma",
        "email": email,
        "phone": phone,
        "address": "123 MG Road, Pune",
        "birthday": "1995-05-15",
    }
    resp = client.post("/api/v1/customers", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Rahul Sharma"
    assert data["phone"] == phone
    assert data["address"] == "123 MG Road, Pune"
    assert data["birthday"] == "1995-05-15"
    assert data["status"] == "active"
    assert data["segment"] == "new"


def test_create_customer_name_validation(tenant_a):
    headers, _ = tenant_a
    base_payload = {
        "phone": random_phone(),
        "email": random_email("name"),
        "address": "123 MG Road, Pune",
        "birthday": "1995-05-15",
    }

    # Missing name
    resp = client.post("/api/v1/customers", json=base_payload, headers=headers)
    assert resp.status_code == 422

    # Null name
    resp = client.post("/api/v1/customers", json={**base_payload, "name": None}, headers=headers)
    assert resp.status_code == 422

    # Empty name
    resp = client.post("/api/v1/customers", json={**base_payload, "name": ""}, headers=headers)
    assert resp.status_code == 422

    # Whitespace only name
    resp = client.post("/api/v1/customers", json={**base_payload, "name": "    "}, headers=headers)
    assert resp.status_code == 422

    # Digits only name rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "name": "123456"}, headers=headers)
    assert resp.status_code == 422

    # Special character only name rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "name": "---@#$"}, headers=headers)
    assert resp.status_code == 422

    # Less than 2 characters
    resp = client.post("/api/v1/customers", json={**base_payload, "name": "A"}, headers=headers)
    assert resp.status_code == 422


def test_create_customer_phone_validation(tenant_a):
    headers, _ = tenant_a
    base_payload = {
        "name": "Amit Patel",
        "email": random_email("amit"),
        "address": "Navrangpura, Ahmedabad",
        "birthday": "1992-08-20",
    }

    # Missing phone
    resp = client.post("/api/v1/customers", json=base_payload, headers=headers)
    assert resp.status_code == 422

    # Null phone
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": None}, headers=headers)
    assert resp.status_code == 422

    # Empty phone
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": ""}, headers=headers)
    assert resp.status_code == 422

    # Whitespace only phone
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": "          "}, headers=headers)
    assert resp.status_code == 422

    # 11-digit phone rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": "98765432101"}, headers=headers)
    assert resp.status_code == 422

    # 9-digit phone rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": "987654321"}, headers=headers)
    assert resp.status_code == 422

    # Starting with invalid digit (< 6, e.g. 5)
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": "5876543210"}, headers=headers)
    assert resp.status_code == 422

    # Alphabetic in phone
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": "98765abcde"}, headers=headers)
    assert resp.status_code == 422

    # Special characters
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": "9876-54321"}, headers=headers)
    assert resp.status_code == 422

    # Valid phone with leading/trailing whitespace should be stripped and accepted
    p_ws = random_phone()
    resp = client.post("/api/v1/customers", json={**base_payload, "phone": f" {p_ws} "}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["phone"] == p_ws


def test_create_customer_address_validation(tenant_a):
    headers, _ = tenant_a
    base_payload = {
        "name": "Suresh Kumar",
        "phone": random_phone(),
        "birthday": "1990-01-01",
    }

    # Missing address rejected
    resp = client.post("/api/v1/customers", json=base_payload, headers=headers)
    assert resp.status_code == 422

    # Null address rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "address": None}, headers=headers)
    assert resp.status_code == 422

    # Empty address string rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "address": ""}, headers=headers)
    assert resp.status_code == 422

    # Whitespace only address rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "address": "     "}, headers=headers)
    assert resp.status_code == 422

    # Valid normal address
    resp = client.post(
        "/api/v1/customers",
        json={**base_payload, "address": "Flat 402, Sunshine Heights, Pune - 411001"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["address"] == "Flat 402, Sunshine Heights, Pune - 411001"


def test_create_customer_birthday_validation(tenant_a):
    headers, _ = tenant_a
    base_payload = {
        "name": "Pooja Verma",
        "address": "Bandra West, Mumbai",
    }

    # 1. Missing / omitted birthday accepted -> 201 + null
    resp_omitted = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone()},
        headers=headers,
    )
    assert resp_omitted.status_code == 201, resp_omitted.text
    assert resp_omitted.json()["birthday"] is None

    # 2. Explicit empty string birthday "" accepted -> 201 + null
    resp_empty = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone(), "birthday": ""},
        headers=headers,
    )
    assert resp_empty.status_code == 201, resp_empty.text
    assert resp_empty.json()["birthday"] is None

    # 3. Explicit whitespace-only birthday "   " accepted -> 201 + null
    resp_ws = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone(), "birthday": "   "},
        headers=headers,
    )
    assert resp_ws.status_code == 201, resp_ws.text
    assert resp_ws.json()["birthday"] is None

    # 4. Explicit null birthday accepted -> 201 + null
    resp_null = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone(), "birthday": None},
        headers=headers,
    )
    assert resp_null.status_code == 201, resp_null.text
    assert resp_null.json()["birthday"] is None

    # 5. Invalid date format rejected -> 422
    resp_inv = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone(), "birthday": "invalid-date"},
        headers=headers,
    )
    assert resp_inv.status_code == 422

    # 6. Future birthdate rejected -> 422
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp_future = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone(), "birthday": tomorrow},
        headers=headers,
    )
    assert resp_future.status_code == 422

    # 7. Valid past birthday accepted -> 201 + date string
    resp_valid = client.post(
        "/api/v1/customers",
        json={**base_payload, "phone": random_phone(), "birthday": "1998-11-25"},
        headers=headers,
    )
    assert resp_valid.status_code == 201, resp_valid.text
    assert resp_valid.json()["birthday"] == "1998-11-25"


def test_list_customers_and_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust_a = create_test_customer(headers_a, name="Tenant A Customer")
    cust_b = create_test_customer(headers_b, name="Tenant B Customer")

    # Tenant A list contains cust_a, but NOT cust_b
    list_a = client.get("/api/v1/customers", headers=headers_a).json()
    ids_a = [c["id"] for c in list_a]
    assert cust_a["id"] in ids_a
    assert cust_b["id"] not in ids_a

    # Tenant B list contains cust_b, but NOT cust_a
    list_b = client.get("/api/v1/customers", headers=headers_b).json()
    ids_b = [c["id"] for c in list_b]
    assert cust_b["id"] in ids_b
    assert cust_a["id"] not in ids_b

    # Search parameter works
    search_resp = client.get("/api/v1/customers", params={"search": "Tenant A"}, headers=headers_a)
    assert search_resp.status_code == 200
    search_ids = [c["id"] for c in search_resp.json()]
    assert cust_a["id"] in search_ids


def test_list_customers_query_param_validation(tenant_a):
    headers, _ = tenant_a

    # Invalid page (0 or negative)
    resp = client.get("/api/v1/customers", params={"page": 0}, headers=headers)
    assert resp.status_code == 422

    resp = client.get("/api/v1/customers", params={"page": -1}, headers=headers)
    assert resp.status_code == 422

    # Invalid page_size (0 or > 100)
    resp = client.get("/api/v1/customers", params={"page_size": 0}, headers=headers)
    assert resp.status_code == 422

    resp = client.get("/api/v1/customers", params={"page_size": 150}, headers=headers)
    assert resp.status_code == 422

    # Invalid status
    resp = client.get("/api/v1/customers", params={"status": "unknown_status"}, headers=headers)
    assert resp.status_code == 422

    # Invalid segment
    resp = client.get("/api/v1/customers", params={"segment": "unknown_seg"}, headers=headers)
    assert resp.status_code == 422

    # Empty / whitespace query parameters
    resp = client.get("/api/v1/customers", params={"name": "   "}, headers=headers)
    assert resp.status_code == 422

    resp = client.get("/api/v1/customers", params={"mobile": "   "}, headers=headers)
    assert resp.status_code == 422

    resp = client.get("/api/v1/customers", params={"search": "   "}, headers=headers)
    assert resp.status_code == 422


def test_customer_stats(tenant_a):
    headers, _ = tenant_a

    # Create customers
    create_test_customer(headers, name="Stats Customer Alpha")
    create_test_customer(headers, name="Stats Customer Beta")

    customers_resp = client.get("/api/v1/customers", headers=headers)
    customers_count = len(customers_resp.json())

    stats_resp = client.get("/api/v1/customers/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()

    assert stats["total_customers"] == customers_count
    assert stats["active_customers"] >= 2
    assert stats["active_customers"] + stats["inactive_customers"] + stats["blocked_customers"] == stats["total_customers"]
    assert stats["new_customers"] + stats["regular_customers"] + stats["vip_customers"] == stats["total_customers"]


def test_feedback_crud_and_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust_a = create_test_customer(headers_a, name="Feedback Cust A")
    cust_b = create_test_customer(headers_b, name="Feedback Cust B")

    # Create feedback for customer A by Tenant A (Must not return 500!)
    fb_resp = client.post(
        "/api/v1/customers/feedback",
        json={"customer_id": cust_a["id"], "rating": 5, "comments": "Excellent pos service"},
        headers=headers_a,
    )
    assert fb_resp.status_code == 201, fb_resp.text
    fb_data = fb_resp.json()
    assert fb_data["customer_id"] == cust_a["id"]
    assert fb_data["rating"] == 5

    # Tenant B cannot create feedback for Tenant A's customer
    cross_resp = client.post(
        "/api/v1/customers/feedback",
        json={"customer_id": cust_a["id"], "rating": 4},
        headers=headers_b,
    )
    assert cross_resp.status_code == 404

    # Invalid customer_id (<= 0) rejected with 422
    inv_resp = client.post(
        "/api/v1/customers/feedback",
        json={"customer_id": -5, "rating": 5},
        headers=headers_a,
    )
    assert inv_resp.status_code == 422

    # Non-existent customer_id rejected with 404
    non_exist_resp = client.post(
        "/api/v1/customers/feedback",
        json={"customer_id": 999999, "rating": 5},
        headers=headers_a,
    )
    assert non_exist_resp.status_code == 404

    # Non-existent invoice_id rejected with 404
    inv_invoice_resp = client.post(
        "/api/v1/customers/feedback",
        json={"customer_id": cust_a["id"], "invoice_id": 999999, "rating": 5},
        headers=headers_a,
    )
    assert inv_invoice_resp.status_code == 404

    # Get feedback by query: Tenant A sees customer A's feedback, Tenant B gets 404
    get_a = client.get("/api/v1/customers/feedback", params={"customer_id": cust_a["id"]}, headers=headers_a)
    assert get_a.status_code == 200
    assert len(get_a.json()) >= 1

    get_cross = client.get("/api/v1/customers/feedback", params={"customer_id": cust_a["id"]}, headers=headers_b)
    assert get_cross.status_code == 404

    # Get feedback by path: /feedback/{customer_id}
    get_path_a = client.get(f"/api/v1/customers/feedback/{cust_a['id']}", headers=headers_a)
    assert get_path_a.status_code == 200
    assert len(get_path_a.json()) >= 1

    get_path_b = client.get(f"/api/v1/customers/feedback/{cust_a['id']}", headers=headers_b)
    assert get_path_b.status_code == 404


def test_wallet_credit_and_debit_response_and_validation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust = create_test_customer(headers_a, name="Wallet Customer")

    ref_cr = str(random.randint(10000000, 99999999))
    ref_db = str(random.randint(10000000, 99999999))

    # Credit wallet: response must include id, reference_no, remarks, amount, balance
    credit_payload = {
        "customer_id": cust["id"],
        "amount": "500.00",
        "reference_no": ref_cr,
        "remarks": "Loyalty bonus credited",
    }
    credit_resp = client.post("/api/v1/customers/wallet/credit", json=credit_payload, headers=headers_a)
    assert credit_resp.status_code == 200, credit_resp.text
    cdata = credit_resp.json()
    assert "id" in cdata
    assert cdata["customer_id"] == cust["id"]
    assert cdata["amount"] == 500.0
    assert cdata["reference_no"] == ref_cr
    assert cdata["remarks"] == "Loyalty bonus credited"
    assert cdata["balance"] == 500.0

    # Debit wallet: response must include id, reference_no, remarks, amount, updated balance
    debit_payload = {
        "customer_id": cust["id"],
        "amount": "200.00",
        "reference_no": ref_db,
        "remarks": "Redeemed for bill",
    }
    debit_resp = client.post("/api/v1/customers/wallet/debit", json=debit_payload, headers=headers_a)
    assert debit_resp.status_code == 200, debit_resp.text
    ddata = debit_resp.json()
    assert "id" in ddata
    assert ddata["amount"] == 200.0
    assert ddata["reference_no"] == ref_db
    assert ddata["remarks"] == "Redeemed for bill"
    assert ddata["balance"] == 300.0

    # Duplicate reference_no rejected with 409 Conflict
    dup_resp = client.post("/api/v1/customers/wallet/credit", json=credit_payload, headers=headers_a)
    assert dup_resp.status_code == 409

    # Valid alphanumeric reference_no such as "REF12345" accepted
    valid_ref_payload = {
        "customer_id": cust["id"],
        "amount": "150.00",
        "reference_no": f"REF{random.randint(10000, 99999)}",
        "remarks": "Alphanumeric ref credit",
    }
    valid_ref_resp = client.post("/api/v1/customers/wallet/credit", json=valid_ref_payload, headers=headers_a)
    assert valid_ref_resp.status_code == 200, valid_ref_resp.text
    assert valid_ref_resp.json()["reference_no"] == valid_ref_payload["reference_no"]

    # Reject unwanted extra field "reason" in Credit and Debit (extra="forbid")
    res_credit_reason = client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "reference_no": f"REF{random.randint(10000, 99999)}", "reason": "Bonus payout"},
        headers=headers_a,
    )
    assert res_credit_reason.status_code == 422, "Credit must reject 'reason' field"

    res_debit_reason = client.post(
        "/api/v1/customers/wallet/debit",
        json={**debit_payload, "reference_no": f"REF{random.randint(10000, 99999)}", "reason": "Bill deduction"},
        headers=headers_a,
    )
    assert res_debit_reason.status_code == 422, "Debit must reject 'reason' field"

    # Customer ID validation: 0, negative, non-existing
    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "customer_id": 0, "reference_no": f"REF{random.randint(10000, 99999)}"},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "customer_id": -1, "reference_no": f"REF{random.randint(10000, 99999)}"},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "customer_id": 999999, "reference_no": f"REF{random.randint(10000, 99999)}"},
        headers=headers_a,
    ).status_code == 404

    # Amount validation: 0, negative, non-numeric
    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "amount": "0", "reference_no": f"REF{random.randint(10000, 99999)}"},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "amount": "-100.00", "reference_no": f"REF{random.randint(10000, 99999)}"},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={**credit_payload, "amount": "abc", "reference_no": f"REF{random.randint(10000, 99999)}"},
        headers=headers_a,
    ).status_code == 422

    # Alphabetic reference_no rejected (ABC, RANDOM, TEST, HELLO, string, abc, CR#12)
    for invalid_ref in ["ABC", "RANDOM", "TEST", "HELLO", "string", "abc", "CR#12"]:
        res = client.post(
            "/api/v1/customers/wallet/credit",
            json={**credit_payload, "reference_no": invalid_ref},
            headers=headers_a,
        )
        assert res.status_code == 422, f"Failed for reference_no={invalid_ref}"

    # Empty reference_no rejected
    empty_ref = {
        "customer_id": cust["id"],
        "amount": "100.00",
        "reference_no": "   ",
        "remarks": "Valid remarks",
    }
    assert client.post("/api/v1/customers/wallet/credit", json=empty_ref, headers=headers_a).status_code == 422

    # Null reference_no rejected
    null_ref = {
        "customer_id": cust["id"],
        "amount": "100.00",
        "reference_no": None,
        "remarks": "Valid remarks",
    }
    assert client.post("/api/v1/customers/wallet/credit", json=null_ref, headers=headers_a).status_code == 422

    # Remarks: missing, null, empty, whitespace rejected
    ref_new = str(random.randint(10000000, 99999999))
    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={"customer_id": cust["id"], "amount": "100.00", "reference_no": ref_new, "remarks": ""},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={"customer_id": cust["id"], "amount": "100.00", "reference_no": ref_new, "remarks": "   "},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={"customer_id": cust["id"], "amount": "100.00", "reference_no": ref_new, "remarks": None},
        headers=headers_a,
    ).status_code == 422

    assert client.post(
        "/api/v1/customers/wallet/credit",
        json={"customer_id": cust["id"], "amount": "100.00", "reference_no": ref_new},
        headers=headers_a,
    ).status_code == 422

    # Insufficient debit
    over_debit = {
        "customer_id": cust["id"],
        "amount": "1000.00",
        "reference_no": str(random.randint(10000000, 99999999)),
        "remarks": "Over limit",
    }
    over_resp = client.post("/api/v1/customers/wallet/debit", json=over_debit, headers=headers_a)
    assert over_resp.status_code == 400

    # Tenant isolation: Tenant B cannot credit Tenant A's customer
    new_credit = {**credit_payload, "reference_no": str(random.randint(10000000, 99999999))}
    assert client.post("/api/v1/customers/wallet/credit", json=new_credit, headers=headers_b).status_code == 404


def test_birthday_endpoint_no_500(tenant_a):
    headers, _ = tenant_a
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Customer with birthday today
    create_test_customer(headers, name="Birthday Boy", birthday=today)
    # Customer with birthday yesterday
    create_test_customer(headers, name="Birthday Yesterday", birthday=yesterday)

    resp = client.get("/api/v1/customers/birthdays", headers=headers)
    assert resp.status_code == 200, resp.text
    b_customers = resp.json()
    assert isinstance(b_customers, list)
    assert any(c["name"] == "Birthday Boy" for c in b_customers)


def test_referrals_endpoint_no_500(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust1 = create_test_customer(headers_a, name="Referrer")
    cust2 = create_test_customer(headers_a, name="Referred")
    cust_b = create_test_customer(headers_b, name="Tenant B Cust")

    # Valid referral (No 500!)
    ref_resp = client.post(
        "/api/v1/customers/referrals",
        json={"customer_id": cust1["id"], "referred_customer_id": cust2["id"]},
        headers=headers_a,
    )
    assert ref_resp.status_code == 200, ref_resp.text
    data = ref_resp.json()
    assert "referral_code" in data
    assert data["customer_id"] == cust1["id"]

    # Duplicate referral rejected with 409
    dup_ref = client.post(
        "/api/v1/customers/referrals",
        json={"customer_id": cust1["id"], "referred_customer_id": cust2["id"]},
        headers=headers_a,
    )
    assert dup_ref.status_code == 409

    # Self referral rejected with 422
    self_ref = client.post(
        "/api/v1/customers/referrals",
        json={"customer_id": cust1["id"], "referred_customer_id": cust1["id"]},
        headers=headers_a,
    )
    assert self_ref.status_code == 422

    # Non-existing referred customer
    non_exist_ref = client.post(
        "/api/v1/customers/referrals",
        json={"customer_id": cust1["id"], "referred_customer_id": 999999},
        headers=headers_a,
    )
    assert non_exist_ref.status_code == 404

    # Cross-tenant referral rejected
    cross_ref = client.post(
        "/api/v1/customers/referrals",
        json={"customer_id": cust1["id"], "referred_customer_id": cust_b["id"]},
        headers=headers_a,
    )
    assert cross_ref.status_code == 404


def test_customer_notes_and_created_by(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    cust = create_test_customer(headers_a, name="Notes Customer")

    # Create note: created_by must match user_a['id'] and not be None
    note_resp = client.post(
        "/api/v1/customers/notes",
        json={"customer_id": cust["id"], "note": "Customer paid ₹500 for order #123. Order is ready at 5:00 PM!"},
        headers=headers_a,
    )
    assert note_resp.status_code == 200, note_resp.text
    note_data = note_resp.json()
    assert note_data["created_by"] is not None
    assert note_data["created_by"] == user_a["id"]
    assert note_data["note"] == "Customer paid ₹500 for order #123. Order is ready at 5:00 PM!"

    # Missing note rejected
    assert client.post(
        "/api/v1/customers/notes",
        json={"customer_id": cust["id"]},
        headers=headers_a,
    ).status_code == 422

    # Null note rejected
    assert client.post(
        "/api/v1/customers/notes",
        json={"customer_id": cust["id"], "note": None},
        headers=headers_a,
    ).status_code == 422

    # Empty note rejected
    assert client.post(
        "/api/v1/customers/notes",
        json={"customer_id": cust["id"], "note": ""},
        headers=headers_a,
    ).status_code == 422

    # Whitespace note rejected
    assert client.post(
        "/api/v1/customers/notes",
        json={"customer_id": cust["id"], "note": "   "},
        headers=headers_a,
    ).status_code == 422

    # Dangerous script injection in note rejected
    for payload in ["<script>alert(1)</script>", "javascript:alert(1)", "<img onerror=alert(1)>", "<iframe src='evil.com'>"]:
        xss_resp = client.post(
            "/api/v1/customers/notes",
            json={"customer_id": cust["id"], "note": payload},
            headers=headers_a,
        )
        assert xss_resp.status_code == 422, f"Failed to reject XSS: {payload}"

    # Invalid customer ID (<= 0)
    inv_resp = client.get("/api/v1/customers/notes", params={"customer_id": 0}, headers=headers_a)
    assert inv_resp.status_code == 422

    # Non-existing customer ID
    assert client.get("/api/v1/customers/notes", params={"customer_id": 999999}, headers=headers_a).status_code == 404

    # Cross-tenant get notes by query and path
    assert client.get("/api/v1/customers/notes", params={"customer_id": cust["id"]}, headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/customers/notes/{cust['id']}", headers=headers_b).status_code == 404


def test_export_directory_parameters(tenant_a):
    headers, _ = tenant_a

    # Default request succeeds
    resp = client.get("/api/v1/customers/export-directory", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # PDF format succeeds
    resp_pdf = client.get("/api/v1/customers/export-directory", params={"format": "pdf"}, headers=headers)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"

    # Explicit empty parameter rejected
    resp_empty = client.get("/api/v1/customers/export-directory", params={"status": ""}, headers=headers)
    assert resp_empty.status_code == 422

    resp_ws = client.get("/api/v1/customers/export-directory", params={"status": "   "}, headers=headers)
    assert resp_ws.status_code == 422

    resp_fmt_empty = client.get("/api/v1/customers/export-directory", params={"format": ""}, headers=headers)
    assert resp_fmt_empty.status_code == 422

    resp_fmt_ws = client.get("/api/v1/customers/export-directory", params={"format": "   "}, headers=headers)
    assert resp_fmt_ws.status_code == 422

    # Invalid status & format
    assert client.get("/api/v1/customers/export-directory", params={"status": "abc"}, headers=headers).status_code == 422
    assert client.get("/api/v1/customers/export-directory", params={"format": "csv"}, headers=headers).status_code == 422
    assert client.get("/api/v1/customers/export-directory", params={"format": "word"}, headers=headers).status_code == 422


def test_update_customer_validation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b
    cust = create_test_customer(headers_a, name="Original Name", birthday="1992-02-02")

    # 1. Normal string placeholder "string" rejected on all normal fields
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "string"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": "string"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": "string"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": "string"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"gstin": "string"}, headers=headers_a).status_code == 422

    # 2. Empty, whitespace, null rejected on normal fields
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": ""}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "   "}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": None}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "1234567"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "!@#$%^"}, headers=headers_a).status_code == 422

    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": ""}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": "   "}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": None}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": "not-an-email"}, headers=headers_a).status_code == 422

    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": ""}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": "   "}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": None}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": "abc"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": "12345"}, headers=headers_a).status_code == 422

    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": ""}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": "   "}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": None}, headers=headers_a).status_code == 422

    assert client.put(f"/api/v1/customers/{cust['id']}", json={"gstin": ""}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"gstin": "   "}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"gstin": None}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"gstin": "INVALIDGSTIN123"}, headers=headers_a).status_code == 422

    # 3. Birthday validation: placeholder, invalid, future rejected
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "string"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "15-05-1995"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "abc"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "1995-99-99"}, headers=headers_a).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": tomorrow}, headers=headers_a).status_code == 422

    # 4. Birthday optional: omitted leaves existing birthday unchanged
    resp_omit = client.put(f"/api/v1/customers/{cust['id']}", json={"name": "Omit Birthday Name"}, headers=headers_a)
    assert resp_omit.status_code == 200
    assert resp_omit.json()["name"] == "Omit Birthday Name"
    assert resp_omit.json()["birthday"] == "1992-02-02"

    # 5. Birthday valid past and today dates accepted
    resp_valid = client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "1995-05-15"}, headers=headers_a)
    assert resp_valid.status_code == 200
    assert resp_valid.json()["birthday"] == "1995-05-15"

    today_str = date.today().isoformat()
    resp_today = client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": today_str}, headers=headers_a)
    assert resp_today.status_code == 200
    assert resp_today.json()["birthday"] == today_str

    # 6. Birthday null, empty, whitespace clears to None
    resp_null = client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": None}, headers=headers_a)
    assert resp_null.status_code == 200
    assert resp_null.json()["birthday"] is None

    # Reset birthday
    client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "1990-01-01"}, headers=headers_a)

    resp_empty = client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": ""}, headers=headers_a)
    assert resp_empty.status_code == 200
    assert resp_empty.json()["birthday"] is None

    # Reset birthday
    client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "1990-01-01"}, headers=headers_a)

    resp_ws = client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": "   "}, headers=headers_a)
    assert resp_ws.status_code == 200
    assert resp_ws.json()["birthday"] is None

    # 7. Non-existing customer and cross-tenant isolation
    assert client.put("/api/v1/customers/999999", json={"name": "Ghost User"}, headers=headers_a).status_code == 404
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "Tenant Attack"}, headers=headers_b).status_code == 404

    # 8. Confirm PATCH route is NOT added (returns 405 Method Not Allowed)
    patch_res = client.patch(f"/api/v1/customers/{cust['id']}", json={"name": "Patch Name"}, headers=headers_a)
    assert patch_res.status_code == 405, "PATCH route must not be added"


def test_loyalty_earn_and_null_points(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust = create_test_customer(headers_a, name="Loyalty Cust")

    # Earn loyalty points (Must not 500 even when customer has initial points 0 or None!)
    resp = client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 150, "reason": "Purchase reward"},
        headers=headers_a,
    )
    assert resp.status_code == 200, resp.text
    ldata = resp.json()
    assert ldata["points_earned"] == 150
    assert ldata["balance_points"] == 150

    # Cross tenant customer earn rejected
    cross_resp = client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 50, "reason": "Bonus points"},
        headers=headers_b,
    )
    assert cross_resp.status_code == 404

    # Non-existing invoice rejected
    assert client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 50, "invoice_id": 999999, "reason": "Invoice points"},
        headers=headers_a,
    ).status_code == 404

    # Redeem loyalty points
    redeem_resp = client.post(
        "/api/v1/customers/loyalty/redeem",
        json={"customer_id": cust["id"], "points": 50},
        headers=headers_a,
    )
    assert redeem_resp.status_code == 200
    assert redeem_resp.json()["balance_points"] == 100

    # Over redeem rejected with 400
    over_resp = client.post(
        "/api/v1/customers/loyalty/redeem",
        json={"customer_id": cust["id"], "points": 500},
        headers=headers_a,
    )
    assert over_resp.status_code == 400


def test_notifications_sms_and_whatsapp(tenant_a):
    headers, _ = tenant_a
    cust = create_test_customer(headers, name="Notification Cust")

    # SMS notification with lowercase "sms" normalized to "SMS"
    sms_resp = client.post(
        "/api/v1/customers/notifications/sms",
        json={"customer_id": cust["id"], "communication_type": "sms", "message": "Your OTP is 123456"},
        headers=headers,
    )
    assert sms_resp.status_code == 200, sms_resp.text
    sms_data = sms_resp.json()
    assert sms_data["communication_type"] == "SMS"
    assert sms_data["message"] == "Your OTP is 123456"

    # GET /notifications/sms
    get_sms = client.get("/api/v1/customers/notifications/sms", headers=headers)
    assert get_sms.status_code == 200
    assert len(get_sms.json()) >= 1

    # WhatsApp notification with lowercase "whatsapp"
    wa_resp = client.post(
        "/api/v1/customers/notifications/whatsapp",
        json={"customer_id": cust["id"], "communication_type": "whatsapp", "message": "Your order is confirmed"},
        headers=headers,
    )
    assert wa_resp.status_code == 200, wa_resp.text
    wa_data = wa_resp.json()
    assert wa_data["communication_type"] == "WHATSAPP"
    assert wa_data["message"] == "Your order is confirmed"

    # GET /notifications/whatsapp
    get_wa = client.get("/api/v1/customers/notifications/whatsapp", headers=headers)
    assert get_wa.status_code == 200
    assert len(get_wa.json()) >= 1

    # WhatsApp endpoint MUST NOT silently convert EMAIL to WHATSAPP -> must return 422
    wa_email = client.post(
        "/api/v1/customers/notifications/whatsapp",
        json={"customer_id": cust["id"], "communication_type": "EMAIL", "message": "Email message"},
        headers=headers,
    )
    assert wa_email.status_code == 422

    # WhatsApp endpoint rejects SMS -> 422
    wa_sms = client.post(
        "/api/v1/customers/notifications/whatsapp",
        json={"customer_id": cust["id"], "communication_type": "SMS", "message": "SMS message"},
        headers=headers,
    )
    assert wa_sms.status_code == 422

    # SMS endpoint rejects WHATSAPP -> 422
    sms_wa = client.post(
        "/api/v1/customers/notifications/sms",
        json={"customer_id": cust["id"], "communication_type": "WHATSAPP", "message": "WhatsApp message"},
        headers=headers,
    )
    assert sms_wa.status_code == 422

    # Missing / empty message rejected
    assert client.post(
        "/api/v1/customers/notifications/sms",
        json={"customer_id": cust["id"], "communication_type": "SMS", "message": ""},
        headers=headers,
    ).status_code == 422


def test_campaign_send_no_500(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust1 = create_test_customer(headers_a, name="Camp Cust One")
    cust2 = create_test_customer(headers_a, name="Camp Cust Two")

    # Valid campaign send with lowercase communication_type (Must not 500!)
    camp_resp = client.post(
        "/api/v1/customers/campaigns/send",
        json={
            "customer_ids": [cust1["id"], cust2["id"]],
            "communication_type": "sms",
            "message": "Diwali Special Offer: 20% off on all items!",
        },
        headers=headers_a,
    )
    assert camp_resp.status_code == 200, camp_resp.text
    assert camp_resp.json()["total_customers"] == 2

    # Empty customer_ids rejected
    assert client.post(
        "/api/v1/customers/campaigns/send",
        json={"customer_ids": [], "communication_type": "sms", "message": "Offer message"},
        headers=headers_a,
    ).status_code == 422

    # Non-positive customer ID rejected
    assert client.post(
        "/api/v1/customers/campaigns/send",
        json={"customer_ids": [-1], "communication_type": "sms", "message": "Offer message"},
        headers=headers_a,
    ).status_code == 422

    # Invalid communication_type rejected
    assert client.post(
        "/api/v1/customers/campaigns/send",
        json={"customer_ids": [cust1["id"]], "communication_type": "telepathy", "message": "Offer message"},
        headers=headers_a,
    ).status_code == 422

    # Customer belonging to another tenant rejected with 404
    assert client.post(
        "/api/v1/customers/campaigns/send",
        json={"customer_ids": [cust1["id"]], "communication_type": "sms", "message": "Offer message"},
        headers=headers_b,
    ).status_code == 404

    # Non-existent customer rejected with 404
    assert client.post(
        "/api/v1/customers/campaigns/send",
        json={"customer_ids": [999999], "communication_type": "sms", "message": "Offer message"},
        headers=headers_a,
    ).status_code == 404


def test_customer_create_valid_names_and_invalid_names(tenant_a):
    headers, _ = tenant_a
    base_payload = {
        "phone": random_phone(),
        "address": "123 Main St, Pune",
        "birthday": "1990-05-15",
    }

    # Valid natural names with letters, spaces, hyphens, apostrophes, periods
    for valid_name in ["Rohan Desai", "O'Connor", "Mary-Jane", "Dr. Amit Patil"]:
        resp = client.post(
            "/api/v1/customers",
            json={**base_payload, "name": valid_name, "phone": random_phone()},
            headers=headers,
        )
        assert resp.status_code == 201, f"Failed for valid name: {valid_name}"
        assert resp.json()["name"] == valid_name

    # Invalid names rejected
    for invalid_name in ["123456", "@@@@@", "---@#$", "!@#$%", "A", "   "]:
        resp = client.post(
            "/api/v1/customers",
            json={**base_payload, "name": invalid_name, "phone": random_phone()},
            headers=headers,
        )
        assert resp.status_code == 422, f"Failed to reject invalid name: {invalid_name}"


def test_customer_list_name_filter_matching_and_unmatched_404(tenant_a):
    headers, _ = tenant_a

    # Create a distinct customer
    cust = create_test_customer(headers, name="Unique Name Alpha")

    # Match found -> 200 with matching customer
    resp_match = client.get("/api/v1/customers", params={"name": "Unique Name Alpha"}, headers=headers)
    assert resp_match.status_code == 200
    results = resp_match.json()
    assert len(results) >= 1
    assert any(c["id"] == cust["id"] for c in results)

    # Specific name filter with no match -> HTTP 404 (not bare 200 [])
    resp_unmatched = client.get("/api/v1/customers", params={"name": "swefghyy"}, headers=headers)
    assert resp_unmatched.status_code == 404, resp_unmatched.text
    assert "swefghyy" in resp_unmatched.json()["detail"]

    # Specific search filter with no match -> HTTP 404
    resp_unmatched_search = client.get("/api/v1/customers", params={"search": "nonexistenttermxyz"}, headers=headers)
    assert resp_unmatched_search.status_code == 404, resp_unmatched_search.text

    # Empty / whitespace name filter -> HTTP 422
    assert client.get("/api/v1/customers", params={"name": "   "}, headers=headers).status_code == 422
    assert client.get("/api/v1/customers", params={"search": "   "}, headers=headers).status_code == 422


def test_customer_subresource_structured_empty_responses(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    # Fresh customer in tenant A with zero sub-resources
    cust = create_test_customer(headers_a, name="Fresh Subresource Cust")
    cid = cust["id"]

    # 1. Orders: customer exists but 0 orders -> structured no-data response
    orders_resp = client.get(f"/api/v1/customers/{cid}/orders", headers=headers_a)
    assert orders_resp.status_code == 200, orders_resp.text
    odata = orders_resp.json()
    assert odata["success"] is True
    assert "No orders found" in odata["message"]
    assert odata["data"] == []

    # 2. Feedback: customer exists but 0 feedback -> structured no-data response
    fb_path_resp = client.get(f"/api/v1/customers/feedback/{cid}", headers=headers_a)
    assert fb_path_resp.status_code == 200, fb_path_resp.text
    fb_data = fb_path_resp.json()
    assert fb_data["success"] is True
    assert "No feedback found" in fb_data["message"]
    assert fb_data["data"] == []

    # Query endpoint delegates to same logic
    fb_query_resp = client.get("/api/v1/customers/feedback", params={"customer_id": cid}, headers=headers_a)
    assert fb_query_resp.status_code == 200
    assert fb_query_resp.json()["data"] == []

    # 3. Wallet transactions: customer exists but 0 transactions -> structured no-data response
    wt_resp = client.get(f"/api/v1/customers/wallet/transactions/{cid}", headers=headers_a)
    assert wt_resp.status_code == 200, wt_resp.text
    wt_data = wt_resp.json()
    assert wt_data["success"] is True
    assert "No wallet transactions found" in wt_data["message"]
    assert wt_data["data"] == []

    # 4. Notes: customer exists but 0 notes -> structured no-data response
    notes_path_resp = client.get(f"/api/v1/customers/notes/{cid}", headers=headers_a)
    assert notes_path_resp.status_code == 200, notes_path_resp.text
    ndata = notes_path_resp.json()
    assert ndata["success"] is True
    assert "No notes found" in ndata["message"]
    assert ndata["data"] == []

    notes_query_resp = client.get("/api/v1/customers/notes", params={"customer_id": cid}, headers=headers_a)
    assert notes_query_resp.status_code == 200
    assert notes_query_resp.json()["data"] == []

    # 5. Loyalty history: customer exists but 0 history -> structured no-data response
    lh_resp = client.get(f"/api/v1/customers/{cid}/loyalty/history", headers=headers_a)
    assert lh_resp.status_code == 200, lh_resp.text
    lh_data = lh_resp.json()
    assert lh_data["success"] is True
    assert "No loyalty history found" in lh_data["message"]
    assert lh_data["data"] == []

    # Cross-tenant and non-existing checks for all sub-resources -> 404
    for endpoint in [
        f"/api/v1/customers/{cid}/orders",
        f"/api/v1/customers/feedback/{cid}",
        f"/api/v1/customers/wallet/transactions/{cid}",
        f"/api/v1/customers/notes/{cid}",
        f"/api/v1/customers/{cid}/loyalty/history",
    ]:
        # Cross-tenant access
        assert client.get(endpoint, headers=headers_b).status_code == 404, f"Cross-tenant leak on {endpoint}"

    for endpoint in [
        "/api/v1/customers/999999/orders",
        "/api/v1/customers/feedback/999999",
        "/api/v1/customers/wallet/transactions/999999",
        "/api/v1/customers/notes/999999",
        "/api/v1/customers/999999/loyalty/history",
    ]:
        # Non-existing access
        assert client.get(endpoint, headers=headers_a).status_code == 404, f"Failed 404 on {endpoint}"


def test_wallet_remarks_and_reference_validation(tenant_a):
    headers, _ = tenant_a
    cust = create_test_customer(headers, name="Wallet Remarks Cust")

    valid_ref = str(random.randint(10000000, 99999999))

    # Reject alphabetic-only, placeholder, empty, whitespace, and special-char reference numbers
    for bad_ref in ["ABC", "RANDOM", "TEST", "HELLO", "string", "abc", "CR#1", "!@#$%", "   ", ""]:
        res = client.post(
            "/api/v1/customers/wallet/credit",
            json={"customer_id": cust["id"], "amount": "100.00", "reference_no": bad_ref, "remarks": "Top-up balance"},
            headers=headers,
        )
        assert res.status_code == 422, f"Failed to reject bad reference_no: {bad_ref}"

    # Accept valid alphanumeric reference numbers (e.g. REF12345, 12345678)
    for good_ref in ["REF12345", "ABC123", "123ABC", valid_ref]:
        ref_unique = f"{good_ref}_{random.randint(100, 999)}"
        res = client.post(
            "/api/v1/customers/wallet/credit",
            json={"customer_id": cust["id"], "amount": "10.00", "reference_no": ref_unique, "remarks": "Top-up balance"},
            headers=headers,
        )
        assert res.status_code == 200, f"Failed to accept valid reference_no: {ref_unique}"

    # Reject invalid remarks (numeric-only, symbol-only, placeholder "string", empty, whitespace, null)
    for bad_remark in ["12345678", "@@@@@", "-------", "!@#$%", "string", "", "   ", None]:
        ref_temp = str(random.randint(10000000, 99999999))
        res = client.post(
            "/api/v1/customers/wallet/credit",
            json={"customer_id": cust["id"], "amount": "100.00", "reference_no": ref_temp, "remarks": bad_remark},
            headers=headers,
        )
        assert res.status_code == 422, f"Failed to reject bad remarks: {bad_remark}"

    # In debit: invalid remarks must fail with 422 BEFORE balance check (even if balance is 0)
    res_debit_bad_remark = client.post(
        "/api/v1/customers/wallet/debit",
        json={"customer_id": cust["id"], "amount": "50000.00", "reference_no": f"REF{random.randint(10000, 99999)}", "remarks": "12345678"},
        headers=headers,
    )
    assert res_debit_bad_remark.status_code == 422, "Invalid remarks should fail with 422 before insufficient balance"

    # Natural-language remarks with legitimate punctuation must be accepted
    good_remarks = [
        "Wallet credit",
        "Customer payment",
        "Refund adjustment",
        "Customer wallet top-up",
        "Cash payment received",
        "Refund adjustment for order #123",
        "Manual wallet credit - approved by manager.",
    ]
    for remark in good_remarks:
        ref_good = str(random.randint(10000000, 99999999))
        res_good = client.post(
            "/api/v1/customers/wallet/credit",
            json={"customer_id": cust["id"], "amount": "10.00", "reference_no": ref_good, "remarks": remark},
            headers=headers,
        )
        assert res_good.status_code == 200, f"Failed to accept valid remark: {remark}"
        assert res_good.json()["remarks"] == remark


def test_loyalty_earn_reason_validation(tenant_a):
    headers, _ = tenant_a
    cust = create_test_customer(headers, name="Loyalty Reason Cust")

    # Reject invalid reason (numeric, symbols, "string", empty, whitespace, missing, null)
    for bad_reason in ["12345", "@@@@", "-------", "string", "", "   ", None]:
        res = client.post(
            "/api/v1/customers/loyalty/earn",
            json={"customer_id": cust["id"], "points": 100, "reason": bad_reason},
            headers=headers,
        )
        assert res.status_code == 422, f"Failed to reject bad reason: {bad_reason}"

    # Missing reason rejected
    res_missing = client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 100},
        headers=headers,
    )
    assert res_missing.status_code == 422

    # Accept valid natural reasons
    for good_reason in ["Purchase reward", "Bonus points for customer purchase", "Promotional loyalty reward"]:
        res_good = client.post(
            "/api/v1/customers/loyalty/earn",
            json={"customer_id": cust["id"], "points": 50, "reason": good_reason},
            headers=headers,
        )
        assert res_good.status_code == 200, f"Failed for good reason: {good_reason}"


def test_list_customers_status_pagination_and_legacy_serialization(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, user_b = tenant_b

    # Create several customers for tenant A
    cust1 = create_test_customer(headers_a, name="Alpha Customer One")
    cust2 = create_test_customer(headers_a, name="Beta Customer Two")
    cust3 = create_test_customer(headers_a, name="Gamma Customer Three")

    # Create a customer for tenant B
    cust_b = create_test_customer(headers_b, name="Tenant B Only Cust")

    # 1. status works independently (active, inactive, blocked) without name/mobile/segment
    res_active = client.get("/api/v1/customers", params={"status": "active"}, headers=headers_a)
    assert res_active.status_code == 200
    active_ids = [c["id"] for c in res_active.json()]
    assert cust1["id"] in active_ids
    assert cust2["id"] in active_ids
    assert cust_b["id"] not in active_ids

    res_inactive = client.get("/api/v1/customers", params={"status": "inactive"}, headers=headers_a)
    assert res_inactive.status_code == 200
    assert isinstance(res_inactive.json(), list)

    res_blocked = client.get("/api/v1/customers", params={"status": "blocked"}, headers=headers_a)
    assert res_blocked.status_code == 200
    assert res_blocked.json() == []  # Empty result returns [] (200 OK), not 404 or 500

    # 2. page works independently
    res_p1 = client.get("/api/v1/customers", params={"page": 1}, headers=headers_a)
    assert res_p1.status_code == 200
    assert len(res_p1.json()) >= 3

    res_p2 = client.get("/api/v1/customers", params={"page": 2}, headers=headers_a)
    assert res_p2.status_code == 200
    assert isinstance(res_p2.json(), list)

    # 3. page_size works independently
    res_ps1 = client.get("/api/v1/customers", params={"page_size": 1}, headers=headers_a)
    assert res_ps1.status_code == 200
    assert len(res_ps1.json()) == 1

    res_ps10 = client.get("/api/v1/customers", params={"page_size": 10}, headers=headers_a)
    assert res_ps10.status_code == 200
    assert len(res_ps10.json()) >= 3

    res_ps100 = client.get("/api/v1/customers", params={"page_size": 100}, headers=headers_a)
    assert res_ps100.status_code == 200

    # 4. Combinations work
    res_comb1 = client.get("/api/v1/customers", params={"page": 1, "page_size": 2}, headers=headers_a)
    assert res_comb1.status_code == 200
    assert len(res_comb1.json()) == 2

    res_comb2 = client.get("/api/v1/customers", params={"status": "active", "page": 1, "page_size": 10}, headers=headers_a)
    assert res_comb2.status_code == 200
    assert len(res_comb2.json()) >= 3

    # 5. Invalid parameters return HTTP 422, NEVER 500
    for bad_status in ["test", "invalid_status", "ACTIVE", "", "   "]:
        res_bad_s = client.get("/api/v1/customers", params={"status": bad_status}, headers=headers_a)
        assert res_bad_s.status_code == 422, f"Expected 422 for status={bad_status}, got {res_bad_s.status_code}"

    for bad_page in [0, -1, "abc", ""]:
        res_bad_p = client.get("/api/v1/customers", params={"page": bad_page}, headers=headers_a)
        assert res_bad_p.status_code == 422, f"Expected 422 for page={bad_page}, got {res_bad_p.status_code}"

    for bad_ps in [0, -1, 101, 150, "abc", ""]:
        res_bad_ps = client.get("/api/v1/customers", params={"page_size": bad_ps}, headers=headers_a)
        assert res_bad_ps.status_code == 422, f"Expected 422 for page_size={bad_ps}, got {res_bad_ps.status_code}"

    # 6. Legacy database record resilience (simulate record with empty segment="")
    from app.core.database import SessionLocal
    from app.models.customer import Customer
    db = SessionLocal()
    try:
        legacy_cust = Customer(
            tenant_id=user_a["tenant_id"],
            name="Legacy Customer Empty Seg",
            phone=random_phone(),
            address="Legacy Address",
            status="active",
            segment="",  # Empty string in database (causes 500 without our fix)
            loyalty_points=0,
            total_spend=0,
        )
        db.add(legacy_cust)
        db.commit()
        db.refresh(legacy_cust)

        # GET with status=active must succeed with 200 (not 500)
        res_legacy_status = client.get("/api/v1/customers", params={"status": "active"}, headers=headers_a)
        assert res_legacy_status.status_code == 200, f"Failed on legacy record with status=active: {res_legacy_status.text}"
        data = res_legacy_status.json()
        leg_entry = next((c for c in data if c["id"] == legacy_cust.id), None)
        assert leg_entry is not None
        assert leg_entry["segment"] in ("new", "regular", "vip", "inactive")

        # GET with page=1 must succeed with 200 (not 500)
        res_legacy_page = client.get("/api/v1/customers", params={"page": 1, "page_size": 10}, headers=headers_a)
        assert res_legacy_page.status_code == 200

        # Legacy database record with empty status=""
        legacy_cust2 = Customer(
            tenant_id=user_a["tenant_id"],
            name="Legacy Customer Empty Status",
            phone=random_phone(),
            address="Legacy Address 2",
            status="",  # Empty string in database
            segment="regular",
            loyalty_points=0,
            total_spend=0,
        )
        db.add(legacy_cust2)
        db.commit()
        db.refresh(legacy_cust2)

        res_legacy_status2 = client.get("/api/v1/customers", headers=headers_a)
        assert res_legacy_status2.status_code == 200
        data2 = res_legacy_status2.json()
        leg_entry2 = next((c for c in data2 if c["id"] == legacy_cust2.id), None)
        assert leg_entry2 is not None
        assert leg_entry2["status"] in ("active", "inactive", "blocked")

        # 7. Mobile filtering
        res_mobile = client.get("/api/v1/customers", params={"mobile": cust1["phone"]}, headers=headers_a)
        assert res_mobile.status_code == 200
        assert any(c["id"] == cust1["id"] for c in res_mobile.json())

        # 8. Segment filtering
        res_seg_new = client.get("/api/v1/customers", params={"segment": "new"}, headers=headers_a)
        assert res_seg_new.status_code == 200
        assert isinstance(res_seg_new.json(), list)

        res_seg_reg = client.get("/api/v1/customers", params={"segment": "regular"}, headers=headers_a)
        assert res_seg_reg.status_code == 200
        assert isinstance(res_seg_reg.json(), list)

        # 9. No matching records on filters (status/segment) returns 200 with [] (never 404/500)
        res_seg_empty = client.get("/api/v1/customers", params={"segment": "inactive"}, headers=headers_a)
        assert res_seg_empty.status_code == 200
        assert res_seg_empty.json() == []

    finally:
        db.close()

