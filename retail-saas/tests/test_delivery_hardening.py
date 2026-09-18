import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from tests.test_delivery import create_delivery_for_tenant, create_order_for_tenant

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
        assert login.status_code == 200, login.text
        data = login.json()
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        user_me = client.get("/api/v1/users/me", headers=headers).json()
        return headers, user_me

    return _create


@pytest.fixture
def tenant_a(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"hard-a-{unique_slug}")
    return headers, user


@pytest.fixture
def tenant_b(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"hard-b-{unique_slug}")
    return headers, user


# ==============================================================================
# 1. POST /api/v1/delivery Hardening (Tracking Number & Delivery Person)
# ==============================================================================

@pytest.mark.parametrize(
    "bad_tracking",
    [
        "123",
        "123456",
        "string",
        "null",
        "none",
        "undefined",
        "------",
        "@@@@",
        "",
        "   ",
    ],
)
def test_post_delivery_tracking_number_invalid_rejected(tenant_a, bad_tracking):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)
    payload = {
        "order_id": order_id,
        "delivery_person": "Valid Courier Boy",
        "tracking_number": bad_tracking,
    }
    resp = client.post("/api/v1/delivery", json=payload, headers=headers)
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "good_tracking",
    [
        "TRK-987654",
        "TRK-RDJ-001",
        "AWB-123456",
        "DLV_99",
        "TRACK#123",
        "IN/2026/001",
    ],
)
def test_post_delivery_tracking_number_valid_accepted(tenant_a, good_tracking):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)
    payload = {
        "order_id": order_id,
        "delivery_person": "Valid Courier Boy",
        "tracking_number": good_tracking,
    }
    resp = client.post("/api/v1/delivery", json=payload, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["data"]["tracking_number"] == good_tracking


@pytest.mark.parametrize(
    "bad_person",
    [
        "12345",
        "string",
        "null",
        "------",
        "@@@###",
        "",
        "   ",
    ],
)
def test_post_delivery_person_invalid_rejected(tenant_a, bad_person):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)
    payload = {
        "order_id": order_id,
        "delivery_person": bad_person,
        "tracking_number": "TRK-987654",
    }
    resp = client.post("/api/v1/delivery", json=payload, headers=headers)
    assert resp.status_code == 422


# ==============================================================================
# 2. PATCH /api/v1/delivery/{id}/partner Reuses Same Validator
# ==============================================================================

def test_patch_delivery_partner_rejection_and_acceptance(tenant_a):
    headers, user = tenant_a
    delivery_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    # Rejected tracking numbers
    for bad_trk in ["123", "string", "123456", "------", ""]:
        resp = client.patch(
            f"/api/v1/delivery/{delivery_id}/partner",
            json={"delivery_person": "Amit Shinde", "tracking_number": bad_trk},
            headers=headers,
        )
        assert resp.status_code == 422, f"Failed for {bad_trk}"

    # Rejected delivery person
    for bad_person in ["12345", "string", "------", ""]:
        resp = client.patch(
            f"/api/v1/delivery/{delivery_id}/partner",
            json={"delivery_person": bad_person, "tracking_number": "TRK-VALID-01"},
            headers=headers,
        )
        assert resp.status_code == 422, f"Failed for {bad_person}"

    # Valid update accepted
    resp = client.patch(
        f"/api/v1/delivery/{delivery_id}/partner",
        json={"delivery_person": "Amit Shinde", "tracking_number": "TRK-VALID-01"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["delivery_person"] == "Amit Shinde"
    assert data["tracking_number"] == "TRK-VALID-01"


# ==============================================================================
# 3. GET /api/v1/delivery/stats Response Structure Hardening
# ==============================================================================

def test_delivery_stats_response_has_stats_only_in_data(tenant_a):
    headers, user = tenant_a
    create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.get("/api/v1/delivery/stats", headers=headers)
    assert resp.status_code == 200
    res = resp.json()

    # Response must have success, message, data
    assert res["success"] is True
    assert "data" in res

    data = res["data"]
    for key in [
        "total_deliveries",
        "pending_deliveries",
        "assigned_deliveries",
        "out_for_delivery_deliveries",
        "delivered_deliveries",
        "cancelled_deliveries",
    ]:
        assert key in data, f"Missing {key} inside data"
        assert key not in res, f"Duplicate {key} found at top-level of response"


# ==============================================================================
# 4. GET /api/v1/delivery/export Hardening (Format Required & Strict)
# ==============================================================================

def test_delivery_export_format_required_no_silent_default(tenant_a):
    headers, _ = tenant_a

    # Missing format must return 422
    resp_missing = client.get("/api/v1/delivery/export", headers=headers)
    assert resp_missing.status_code == 422

    # Invalid formats must return 422
    for bad_fmt in ["pdf", "json", "xml", "txt", "string", "123"]:
        resp_bad = client.get(f"/api/v1/delivery/export?format={bad_fmt}", headers=headers)
        assert resp_bad.status_code == 422, f"Failed for {bad_fmt}"

    # Valid formats return 200
    resp_excel = client.get("/api/v1/delivery/export?format=excel", headers=headers)
    assert resp_excel.status_code == 200
    assert "spreadsheetml" in resp_excel.headers.get("content-type", "")

    resp_csv = client.get("/api/v1/delivery/export?format=csv", headers=headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers.get("content-type", "")


# ==============================================================================
# 5. PATCH /api/v1/delivery/{id}/cancel Hardening (Reason Required & Conflict)
# ==============================================================================

def test_delivery_cancel_reason_hardening_and_409_state_conflict(tenant_a):
    headers, user = tenant_a
    delivery_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    # Missing body or empty body returns 422
    assert client.patch(f"/api/v1/delivery/{delivery_id}/cancel", headers=headers).status_code == 422
    assert client.patch(f"/api/v1/delivery/{delivery_id}/cancel", json={}, headers=headers).status_code == 422

    # Invalid reasons return 422
    for bad_reason in ["string", "null", "123456", "------", "", "   "]:
        resp = client.patch(
            f"/api/v1/delivery/{delivery_id}/cancel",
            json={"reason": bad_reason},
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for reason='{bad_reason}', got {resp.status_code}"

    # Valid reason successfully cancels
    valid_reason = "Customer cancelled order before shipping"
    resp_cancel = client.patch(
        f"/api/v1/delivery/{delivery_id}/cancel",
        json={"reason": valid_reason},
        headers=headers,
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["data"]["status"] == "cancelled"

    # Preserved Business Conflict: Attempting to cancel already-cancelled returns 409 (not 422)
    resp_conflict = client.patch(
        f"/api/v1/delivery/{delivery_id}/cancel",
        json={"reason": valid_reason},
        headers=headers,
    )
    assert resp_conflict.status_code == 409


# ==============================================================================
# 6. Delivery Methods Hardening (Cost Zero Behavior, Positive Days, Strict Bool)
# ==============================================================================

def test_delivery_methods_cost_and_days_hardening(tenant_a):
    headers, _ = tenant_a

    # Cost = 0.00 is explicitly allowed
    resp_zero_cost = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "Free Store Pickup",
            "code": "FREE_PICKUP_001",
            "description": "Free customer pickup at store counter",
            "cost": 0.00,
            "estimated_days": 1,
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_zero_cost.status_code == 201
    assert float(resp_zero_cost.json()["data"]["cost"]) == 0.00

    # Negative cost is rejected
    resp_neg_cost = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "Negative Cost Method",
            "code": "NEG_METH_001",
            "description": "Negative cost test description",
            "cost": -5.00,
        },
        headers=headers,
    )
    assert resp_neg_cost.status_code == 422

    # Estimated days <= 0 or float is rejected
    for bad_days in [0, -1, 2.5, "3", "string"]:
        resp_days = client.post(
            "/api/v1/delivery/methods",
            json={
                "name": "Invalid Days Method",
                "code": "INV_DAYS_001",
                "description": "Invalid days test description",
                "estimated_days": bad_days,
            },
            headers=headers,
        )
        assert resp_days.status_code == 422, f"Failed for days={bad_days}"

    # Strict boolean on is_active: non-booleans rejected
    for bad_bool in ["true", "false", 1, 0, "1", "0"]:
        resp_bool = client.post(
            "/api/v1/delivery/methods",
            json={
                "name": "Invalid Bool Method",
                "code": "INV_BOOL_001",
                "description": "Invalid bool test description",
                "is_active": bad_bool,
            },
            headers=headers,
        )
        assert resp_bool.status_code == 422, f"Failed for bool={bad_bool}"


# ==============================================================================
# 7. Delivery Zones Hardening (6-digit Indian PIN, Placeholders Rejected)
# ==============================================================================

def test_delivery_zones_pincode_validation(tenant_a):
    headers, _ = tenant_a

    # Invalid pincodes list
    for bad_pins in [
        ["123"],          # too short
        ["1234567"],      # too long
        ["012345"],       # starts with 0
        ["ABCDEF"],       # alphabetic
        ["40000A"],       # alphanumeric
        ["400 01"],       # spaces
        [],               # empty list
    ]:
        resp = client.post(
            "/api/v1/delivery/zones",
            json={
                "name": "Invalid Pin Zone",
                "code": "INV_PIN_ZONE",
                "description": "Zone with invalid pin",
                "pincodes": bad_pins,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Failed for pincodes={bad_pins}"

    # Valid 6-digit PIN codes
    resp_valid = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "Valid Mumbai Zone",
            "code": "VAL_MUM_ZONE_01",
            "description": "Valid zone with 6-digit Indian PIN codes",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincodes": ["400001", "400012", "400050"],
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_valid.status_code == 201


# ==============================================================================
# 8. Delivery Partners Hardening (Indian Mobile, Credentials, Tracking URL)
# ==============================================================================

def test_delivery_partners_phone_and_url_hardening(tenant_a):
    headers, _ = tenant_a

    # Invalid phone numbers
    for bad_phone in [
        "1234567890",       # starts with 1
        "5555555555",       # starts with 5
        "09876543210",      # 11 digits with 0
        "+911234567890",    # +91 with invalid 1-prefix
        "987654321",        # 9 digits
        "98765432100",      # 11 digits
        "phone_number",     # letters
    ]:
        resp = client.post(
            "/api/v1/delivery/partners/connect",
            json={
                "name": "Bad Phone Partner",
                "code": "BAD_PHONE_PART",
                "description": "Test partner description",
                "contact_phone": bad_phone,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Failed for phone={bad_phone}"

    # Valid Indian phones (both 10-digit and +91 formats)
    for idx, good_phone in enumerate(["9876543210", "+919876543210"]):
        resp = client.post(
            "/api/v1/delivery/partners/connect",
            json={
                "name": f"Partner Phone {idx}",
                "code": f"PART_PH_{idx}",
                "description": "Test partner description",
                "contact_phone": good_phone,
            },
            headers=headers,
        )
        assert resp.status_code == 201

    # Invalid tracking URL template
    for bad_url in ["string", "null", "httptest", "ftp://carrier.com", "http://"]:
        resp = client.post(
            "/api/v1/delivery/partners/connect",
            json={
                "name": "Bad URL Partner",
                "code": "BAD_URL_PART",
                "description": "Test partner description",
                "tracking_url_template": bad_url,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Failed for url={bad_url}"


# ==============================================================================
# 9. PATCH /api/v1/delivery/{id}/address Hardening (Real-World Address)
# ==============================================================================

def test_delivery_address_update_hardening(tenant_a):
    headers, user = tenant_a
    delivery_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    # Letters-only NOT enforced: real-world addresses with numbers, commas, slashes, PIN accepted
    real_address = "Flat 402, Building 7, B-Wing, MG Road, Sector 15, Pune - 411001"
    resp_ok = client.patch(
        f"/api/v1/delivery/{delivery_id}/address",
        json={"delivery_address": real_address},
        headers=headers,
    )
    assert resp_ok.status_code == 200

    # Placeholders, numeric-only, special-only rejected
    for bad_addr in ["string", "12345678", "------", "@@@###", "", "   "]:
        resp_bad = client.patch(
            f"/api/v1/delivery/{delivery_id}/address",
            json={"delivery_address": bad_addr},
            headers=headers,
        )
        assert resp_bad.status_code == 422, f"Failed for address='{bad_addr}'"


# ==============================================================================
# 10. Serviceability Pincode Path Param Hardening
# ==============================================================================

def test_serviceability_path_pincode_validation(tenant_a):
    headers, _ = tenant_a

    # Invalid path pincodes
    for bad_pin in ["12345", "1234567", "012345", "ABCDEF", "string"]:
        resp = client.get(f"/api/v1/delivery/serviceability/{bad_pin}", headers=headers)
        assert resp.status_code == 422, f"Failed for pincode={bad_pin}"

    # Structurally valid Indian PIN code (returns 200 with serviceability result)
    resp_ok = client.get("/api/v1/delivery/serviceability/400001", headers=headers)
    assert resp_ok.status_code == 200
    assert "is_serviceable" in resp_ok.json()["data"]


# ==============================================================================
# 11. Tenant Isolation Verification Across Modules (404, Not 422 or 500)
# ==============================================================================

def test_delivery_tenant_isolation_returns_404(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, user_b = tenant_b

    # Create resources in Tenant A
    delivery_id, _ = create_delivery_for_tenant(headers_a, user_a, initial_status="pending")

    method_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Tenant A Method", "code": "T_A_ISOL_METH", "description": "Tenant A method desc"},
        headers=headers_a,
    )
    method_id = method_resp.json()["data"]["id"]

    zone_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Tenant A Zone", "code": "T_A_ISOL_ZONE", "description": "Tenant A zone desc", "pincodes": ["400001"]},
        headers=headers_a,
    )
    zone_id = zone_resp.json()["data"]["id"]

    partner_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Tenant A Partner", "code": "T_A_ISOL_PART", "description": "Tenant A partner desc"},
        headers=headers_a,
    )
    partner_id = partner_resp.json()["data"]["id"]

    # Tenant B accessing Tenant A resources must receive 404 (not 422, not 500)
    assert client.get(f"/api/v1/delivery/{delivery_id}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/delivery/{delivery_id}/tracking", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/delivery/{delivery_id}/history", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/delivery/{delivery_id}/label", headers=headers_b).status_code == 404
    assert client.put(f"/api/v1/delivery/methods/{method_id}", json={"name": "Hacked"}, headers=headers_b).status_code == 404
    assert client.put(f"/api/v1/delivery/zones/{zone_id}", json={"name": "Hacked"}, headers=headers_b).status_code == 404
    assert client.put(f"/api/v1/delivery/partners/{partner_id}", json={"name": "Hacked"}, headers=headers_b).status_code == 404
