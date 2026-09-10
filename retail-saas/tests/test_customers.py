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
        "phone": random_phone(),
        "address": "Bandra West, Mumbai",
    }

    # Missing birthday rejected
    resp = client.post("/api/v1/customers", json=base_payload, headers=headers)
    assert resp.status_code == 422

    # Null birthday rejected
    resp = client.post("/api/v1/customers", json={**base_payload, "birthday": None}, headers=headers)
    assert resp.status_code == 422

    # Invalid date format
    resp = client.post("/api/v1/customers", json={**base_payload, "birthday": "invalid-date"}, headers=headers)
    assert resp.status_code == 422

    # Future birthdate rejected
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.post("/api/v1/customers", json={**base_payload, "birthday": tomorrow}, headers=headers)
    assert resp.status_code == 422

    # Valid past birthday accepted
    resp = client.post("/api/v1/customers", json={**base_payload, "birthday": "1998-11-25"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["birthday"] == "1998-11-25"


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
    create_test_customer(headers, name="Stats Cust 1")
    create_test_customer(headers, name="Stats Cust 2")

    customers_resp = client.get("/api/v1/customers", headers=headers)
    customers_count = len(customers_resp.json())

    stats_resp = client.get("/api/v1/customers/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()

    assert stats["total_customers"] == customers_count
    assert stats["active_customers"] >= 2


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

    # Alphabetic reference_no rejected (ABC, RANDOM, TEST, HELLO)
    for invalid_ref in ["ABC", "RANDOM", "TEST", "HELLO", "TXN-001", "CR#12"]:
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


def test_update_customer_validation(tenant_a):
    headers, _ = tenant_a
    cust = create_test_customer(headers, name="Original Name")

    # Invalid name (digits only, special chars, whitespace)
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "1234567"}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "!@#$%^"}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"name": "   "}, headers=headers).status_code == 422

    # Invalid email
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": "not-an-email"}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"email": "   "}, headers=headers).status_code == 422

    # Empty / null address
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": ""}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": "   "}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"address": None}, headers=headers).status_code == 422

    # Future / null / empty birthday
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": tomorrow}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": ""}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"birthday": None}, headers=headers).status_code == 422

    # Phone update validation
    assert client.put(f"/api/v1/customers/{cust['id']}", json={"phone": "12345"}, headers=headers).status_code == 422

    # Valid update
    resp = client.put(
        f"/api/v1/customers/{cust['id']}",
        json={"name": "Updated Valid Name", "address": "New Valid Address", "birthday": "1994-04-14"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Valid Name"
    assert resp.json()["address"] == "New Valid Address"
    assert resp.json()["birthday"] == "1994-04-14"


def test_loyalty_earn_and_null_points(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    cust = create_test_customer(headers_a, name="Loyalty Cust")

    # Earn loyalty points (Must not 500 even when customer has initial points 0 or None!)
    resp = client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 150},
        headers=headers_a,
    )
    assert resp.status_code == 200, resp.text
    ldata = resp.json()
    assert ldata["points_earned"] == 150
    assert ldata["balance_points"] == 150

    # Cross tenant customer earn rejected
    cross_resp = client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 50},
        headers=headers_b,
    )
    assert cross_resp.status_code == 404

    # Non-existing invoice rejected
    assert client.post(
        "/api/v1/customers/loyalty/earn",
        json={"customer_id": cust["id"], "points": 50, "invoice_id": 999999},
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

    cust1 = create_test_customer(headers_a, name="Camp Cust 1")
    cust2 = create_test_customer(headers_a, name="Camp Cust 2")

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
