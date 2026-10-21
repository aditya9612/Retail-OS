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

    # Rejected delivery person (e.g. numeric "11", "12345", "string", "------", "")
    for bad_person in ["11", "00", "12345", "string", "------", "!@#$%", "pppp", "@#e0", ""]:
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
    for bad_fmt in ["yaml", "json", "xml", "txt", "string", "123"]:
        resp_bad = client.get(f"/api/v1/delivery/export?format={bad_fmt}", headers=headers)
        assert resp_bad.status_code == 422, f"Failed for {bad_fmt}"

    # Valid formats return 200
    resp_excel = client.get("/api/v1/delivery/export?format=excel", headers=headers)
    assert resp_excel.status_code == 200
    assert "spreadsheetml" in resp_excel.headers.get("content-type", "")

    resp_csv = client.get("/api/v1/delivery/export?format=csv", headers=headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers.get("content-type", "")

    resp_pdf = client.get("/api/v1/delivery/export?format=pdf", headers=headers)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers.get("content-type", "") == "application/pdf"
    assert "deliveries.pdf" in resp_pdf.headers.get("content-disposition", "")
    assert resp_pdf.content.startswith(b"%PDF-")


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

    # Zero cost (0.00) is rejected with 422
    resp_zero_cost = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "Zero Cost Method",
            "code": "ZERO_COST_001",
            "description": "Zero cost test description",
            "cost": 0.00,
            "estimated_days": 1,
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_zero_cost.status_code == 422

    # Positive cost is accepted
    resp_pos_cost = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "Standard Store Pickup",
            "code": "STD_PICKUP_001",
            "description": "Customer pickup at store counter",
            "cost": 5.00,
            "estimated_days": 1,
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_pos_cost.status_code == 201
    assert float(resp_pos_cost.json()["data"]["cost"]) == 5.00

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
        json={"name": "Tenant A Method", "code": "T_A_ISOL_METH", "description": "Tenant A method desc", "cost": 10.00},
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


# ==============================================================================
# 12. Strict Delivery Method Field Validations Hardening
# ==============================================================================

def test_delivery_methods_strict_validation_hardening(tenant_a):
    headers, _ = tenant_a

    # 1. Invalid names: "d0", "123445", "!@##$%", "ppppp", "p0@#$", symbol spam, placeholders
    invalid_names = [
        "d0",
        "123445",
        "!@##$%",
        "ppppp",
        "p0@#$",
        "string",
        "null",
        "none",
        "----",
        "++++",
        "(())",
        "[[]]",
        "{{}}",
        "\\\\\\",
        "||",
        ";;;",
        ":::",
        "???",
        ">>>",
        "<<<",
        "////",
    ]
    for bad_name in invalid_names:
        resp = client.post(
            "/api/v1/delivery/methods",
            json={
                "name": bad_name,
                "code": "VALID_CODE_01",
                "description": "Valid descriptive text",
                "cost": 15.00,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for bad name '{bad_name}', got {resp.status_code}"

    # 2. Invalid codes: "d000", "0000", "d0", "AAAA", "123445", "!@##$%", "p0@#$", "----"
    invalid_codes = [
        "d000",
        "0000",
        "d0",
        "AAAA",
        "123445",
        "!@##$%",
        "p0@#$",
        "----",
        "string",
    ]
    for bad_code in invalid_codes:
        resp = client.post(
            "/api/v1/delivery/methods",
            json={
                "name": "Valid Method Name",
                "code": bad_code,
                "description": "Valid descriptive text",
                "cost": 15.00,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for bad code '{bad_code}', got {resp.status_code}"

    # 3. Invalid descriptions: "00-", "123445", "!@##$%", "ppppp", symbol spam
    invalid_descriptions = [
        "00-",
        "123445",
        "!@##$%",
        "ppppp",
        "string",
        "\\\\\\",
        "----",
    ]
    for bad_desc in invalid_descriptions:
        resp = client.post(
            "/api/v1/delivery/methods",
            json={
                "name": "Valid Method Name",
                "code": "VALID_CODE_02",
                "description": bad_desc,
                "cost": 15.00,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for bad desc '{bad_desc}', got {resp.status_code}"

    # 4. Estimated days: 365 rejected, 60 accepted
    resp_365 = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "Standard Delivery",
            "code": "STD_DLV_01",
            "description": "Standard delivery service",
            "cost": 25.00,
            "estimated_days": 365,
        },
        headers=headers,
    )
    assert resp_365.status_code == 422

    # Valid method creation succeeds
    resp_ok = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "Standard Delivery",
            "code": "STD_DLV_01",
            "description": "Standard delivery service within 3 business days",
            "cost": 25.00,
            "estimated_days": 3,
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_ok.status_code == 201
    assert resp_ok.json()["data"]["name"] == "Standard Delivery"
    assert resp_ok.json()["data"]["code"] == "STD_DLV_01"
    assert resp_ok.json()["data"]["estimated_days"] == 3


# ==============================================================================
# 13. PUT Delivery Method Malformed JSON Error Message Specifies Expected Value
# ==============================================================================

def test_delivery_method_update_malformed_json_specifies_expected_value(tenant_a):
    headers, _ = tenant_a

    # Create a delivery method first
    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={
            "name": "SwiftShip Logistics",
            "code": "SSL-PUNE-02",
            "description": "Fast and secure delivery service for retail orders",
            "cost": 200.0,
            "estimated_days": 2,
            "is_active": True,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    # Send malformed JSON payload where "is_active": has no value
    raw_headers = dict(headers)
    raw_headers["Content-Type"] = "application/json"
    malformed_body = b'{\n  "is_active":\n}'

    resp = client.put(
        f"/api/v1/delivery/methods/{method_id}",
        content=malformed_body,
        headers=raw_headers,
    )
    assert resp.status_code == 422
    res = resp.json()

    # Must NOT report "field: '18'" or generic "JSON decode error" without expected value
    assert "18" not in res["message"]
    assert "is_active" in res["message"]
    assert "Expected a boolean" in res["message"]
    assert res["errors"][0]["field"] == "is_active"
    assert "Expected a boolean" in res["errors"][0]["message"]


def test_delivery_zone_update_malformed_json_specifies_expected_value(tenant_a):
    headers, _ = tenant_a

    # Create a delivery zone first
    create_resp = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "Pune Camp Zone",
            "code": "PUN-CAMP-01",
            "description": "Pune Camp and Cantonment zone",
            "city": "Pune",
            "state": "Maharashtra",
            "pincodes": ["411001"],
            "is_active": True,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    zone_id = create_resp.json()["data"]["id"]

    # Send malformed JSON payload where "is_active": has no value (exact user screenshot scenario)
    raw_headers = dict(headers)
    raw_headers["Content-Type"] = "application/json"
    malformed_body = b'{\n  "is_active":\n}'

    resp = client.put(
        f"/api/v1/delivery/zones/{zone_id}",
        content=malformed_body,
        headers=raw_headers,
    )
    assert resp.status_code == 422
    res = resp.json()

    # Must NOT report "field: '21'" or generic "JSON decode error" without expected value
    assert "21" not in res["message"]
    assert "is_active" in res["message"]
    assert "Expected a boolean" in res["message"]
    assert res["errors"][0]["field"] == "is_active"
    assert "Expected a boolean" in res["errors"][0]["message"]


def test_delivery_zones_geo_and_text_hardening(tenant_a):
    headers, _ = tenant_a

    # 1. Exact invalid payload reported by QA/User
    resp_screenshot = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "ww",
            "code": "W000",
            "description": "00-",
            "city": "maharashtra",
            "state": "pune",
            "pincodes": ["415516"],
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_screenshot.status_code == 422

    # 2. Reject state as a city (e.g. city='Maharashtra' or 'Gujarat')
    for bad_city in ["maharashtra", "Maharashtra", "Gujarat", "Karnataka", "india", "japan"]:
        resp = client.post(
            "/api/v1/delivery/zones",
            json={
                "name": "Valid Zone Name",
                "code": "VAL_ZONE_GEO1",
                "description": "Valid zone description",
                "city": bad_city,
                "state": "Maharashtra",
                "pincodes": ["400001"],
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for city='{bad_city}'"

    # 3. Reject city as a state (e.g. state='pune' or 'mumbai')
    for bad_state in ["pune", "Pune", "Mumbai", "Nagpur", "random_state", "12345", "!@#$%"]:
        resp = client.post(
            "/api/v1/delivery/zones",
            json={
                "name": "Valid Zone Name",
                "code": "VAL_ZONE_GEO2",
                "description": "Valid zone description",
                "city": "Pune",
                "state": bad_state,
                "pincodes": ["411001"],
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for state='{bad_state}'"

    # 4. Reject Pincode that does not match State (e.g. state='Gujarat' with Maharashtra pincode 415516)
    resp_pincode_mismatch = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "Gujarat Zone",
            "code": "GJ_ZONE_01",
            "description": "Gujarat zone description",
            "city": "Surat",
            "state": "Gujarat",
            "pincodes": ["415516"],
        },
        headers=headers,
    )
    assert resp_pincode_mismatch.status_code == 422
    assert "Pincode '415516' does not belong to state 'Gujarat'" in resp_pincode_mismatch.json()["message"]

    # 5. Reject City that does not match State (e.g. city='Pune' with state='Gujarat')
    resp_city_state_mismatch = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "Mismatched Zone",
            "code": "MISMATCH_ZONE_01",
            "description": "Valid zone description",
            "city": "Pune",
            "state": "Gujarat",
            "pincodes": ["380001"],
        },
        headers=headers,
    )
    assert resp_city_state_mismatch.status_code == 422
    assert "belongs to state 'Maharashtra'" in resp_city_state_mismatch.json()["message"]

    # 6. Reject invalid names, codes, descriptions, and spam symbols
    for bad_name in ["ww", "pppp", "12345", "!@#$%", "---", "   ", ""]:
        resp = client.post(
            "/api/v1/delivery/zones",
            json={"name": bad_name, "code": "VAL_ZONE_SPAM", "pincodes": ["400001"]},
            headers=headers,
        )
        assert resp.status_code == 422

    for bad_code in ["W000", "w0@", "12345", "!@#$%", "---", "   ", ""]:
        resp = client.post(
            "/api/v1/delivery/zones",
            json={"name": "Valid Zone Name", "code": bad_code, "pincodes": ["400001"]},
            headers=headers,
        )
        assert resp.status_code == 422

    for bad_desc in ["00-", "---", "12345", "!@#$%", "pppp", "w0@"]:
        resp = client.post(
            "/api/v1/delivery/zones",
            json={"name": "Valid Zone Name", "code": "VAL_ZONE_DESC", "description": bad_desc, "pincodes": ["400001"]},
            headers=headers,
        )
        assert resp.status_code == 422

    # 7. Reject Pincode that matches State but does NOT match City (e.g. city='Mumbai' with Satara pincode '415516')
    resp_city_pincode_mismatch = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "Mumbai Central Zone",
            "code": "MUMBAI-CENTRAL-01",
            "description": "Delivery zone covering Mumbai residential areas",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincodes": ["415516"],
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_city_pincode_mismatch.status_code == 422
    assert "Pincode '415516' does not match city 'Mumbai'" in resp_city_pincode_mismatch.json()["message"]

    # 8. Valid delivery zone creates successfully
    resp_ok = client.post(
        "/api/v1/delivery/zones",
        json={
            "name": "West Zone Pune",
            "code": "WZ-PUN-01",
            "description": "Pune West Zone coverage belt",
            "city": "Pune",
            "state": "Maharashtra",
            "pincodes": ["411001", "411004"],
            "is_active": True,
        },
        headers=headers,
    )
    assert resp_ok.status_code == 201
    zone = resp_ok.json()["data"]
    assert zone["name"] == "West Zone Pune"
    assert zone["code"] == "WZ-PUN-01"
    assert zone["city"] == "Pune"
    assert zone["state"] == "Maharashtra"
    assert "411001" in zone["pincodes"]


def test_delivery_partner_connect_hardening(tenant_a):
    headers, _ = tenant_a

    base_payload = {
        "name": "Delhivery Express",
        "code": "DELHIVERY_EXP",
        "description": "National express courier partner",
        "contact_email": "support@delhivery.com",
        "contact_phone": "+919876543210",
        "api_key": "live_key_delhivery_12345",
        "api_secret": "live_secret_delhivery_67890",
        "tracking_url_template": "https://delhivery.com/track/{tracking_number}",
        "is_active": True,
    }

    # 1. Invalid contact email rejected (e.g. "---@PP.COM", "!@#$%", "pppp")
    for bad_email in ["---@PP.COM", "!@#$%", "pppp", "string", "12345"]:
        payload = dict(base_payload)
        payload["contact_email"] = bad_email
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad email: {bad_email}"

    # 2. Invalid contact phone rejected (e.g. 9 digits "600000000", dummy 10 digits "6000000000", "!@#$%", "pppp", "0000000000")
    for bad_phone in ["600000000", "6000000000", "7000000000", "9999999999", "6111111111", "12345", "!@#$%", "pppp", "0000000000", "5555555555"]:
        payload = dict(base_payload)
        payload["contact_phone"] = bad_phone
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad phone: {bad_phone}"

    # 3. Invalid name and code rejected (e.g. "00", "0000", "!@#$%", "pppp", "@#e0")
    for bad_name in ["00", "12345", "!@#$%", "pppp", "@#e0", "----", ""]:
        payload = dict(base_payload)
        payload["name"] = bad_name
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad name: {bad_name}"

    for bad_code in ["0000", "12345", "!@#$%", "pppp", "@#e0", "----", ""]:
        payload = dict(base_payload)
        payload["code"] = bad_code
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad code: {bad_code}"

    # 4. Invalid tracking url rejected (e.g. "https://0000", "https://----", "!@#$%", "string")
    for bad_url in ["https://0000", "https://----", "https://!@#$%", "string", "pppp", "http://1234"]:
        payload = dict(base_payload)
        payload["tracking_url_template"] = bad_url
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad tracking url: {bad_url}"

    # 5. Invalid description rejected (e.g. "0P", "!@#$%", "pppp", "@#e0")
    for bad_desc in ["0P", "!@#$%", "pppp", "@#e0", "----", ""]:
        payload = dict(base_payload)
        payload["description"] = bad_desc
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad description: {bad_desc}"

    # 6. Invalid API key and secret rejected (e.g. "0-0", "12345", "!@#$%", "pppp", "@#e0")
    for bad_cred in ["0-0", "12345", "!@#$%", "pppp", "@#e0", "------"]:
        payload = dict(base_payload)
        payload["api_key"] = bad_cred
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad api_key: {bad_cred}"

        payload = dict(base_payload)
        payload["api_secret"] = bad_cred
        resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
        assert resp.status_code == 422, f"Expected 422 for bad api_secret: {bad_cred}"

    # 7. Valid partner connects successfully
    resp_ok = client.post("/api/v1/delivery/partners/connect", json=base_payload, headers=headers)
    assert resp_ok.status_code == 201
    partner = resp_ok.json()["data"]
    assert partner["name"] == "Delhivery Express"
    assert partner["code"] == "DELHIVERY_EXP"
    assert partner["contact_email"] == "support@delhivery.com"
    assert partner["contact_phone"] == "+919876543210"
    assert partner["tracking_url_template"] == "https://delhivery.com/track/{tracking_number}"
    assert partner["is_active"] is True


def test_delivery_partner_connect_malformed_json_specifies_expected_value(tenant_a):
    headers, _ = tenant_a
    raw_headers = dict(headers)
    raw_headers["Content-Type"] = "application/json"

    # User screenshot payload with "is_active": lacking a value
    malformed_body = b'''{
  "name": "Delhivery Express",
  "code": "DELHIVERY_EXP",
  "description": "National express courier partner",
  "contact_email": "support@delhivery.com",
  "contact_phone": "+919876543210",
  "api_key": "live_key_delhivery_12345",
  "api_secret": "live_secret_delhivery_67890",
  "tracking_url_template": "https://delhivery.com/track/{tracking_number}",
  "is_active":
}'''

    resp = client.post(
        "/api/v1/delivery/partners/connect",
        content=malformed_body,
        headers=raw_headers,
    )
    assert resp.status_code == 422
    res = resp.json()
    assert "is_active" in res["message"]
    assert "Expected a boolean" in res["message"]
    assert res["errors"][0]["field"] == "is_active"
    assert "Expected a boolean" in res["errors"][0]["message"]


def test_delivery_history_status_matches_list_api(tenant_a):
    headers, user = tenant_a
    from app.core.database import SessionLocal
    from app.models.delivery import Delivery
    from app.models.order import Order, OrderTracking
    from app.models.store import Store
    import uuid

    db = SessionLocal()
    try:
        tenant_id = user["tenant_id"]
        uid = uuid.uuid4().hex[:8]
        store = Store(tenant_id=tenant_id, name=f"Store {uid}", code=f"ST-{uid}")
        db.add(store)
        db.flush()

        order = Order(
            tenant_id=tenant_id,
            store_id=store.id,
            order_number=f"ORD-{uid}",
            order_type="pos",
            status="confirmed",
        )
        db.add(order)
        db.flush()

        # Simulate user screenshot scenario:
        # Order tracking has status="confirmed", delivery has status="pending"
        delivery = Delivery(
            tenant_id=tenant_id,
            order_id=order.id,
            status="pending",
        )
        db.add(delivery)

        order_tracking = OrderTracking(
            order_id=order.id,
            status="confirmed",
            remarks="Order confirmed",
        )
        db.add(order_tracking)
        db.commit()
        db.refresh(delivery)
        del_id = delivery.id
    finally:
        db.close()

    # 1. Check List API status: delivery is "pending"
    list_resp = client.get("/api/v1/delivery", headers=headers)
    assert list_resp.status_code == 200
    deliveries = list_resp.json()["data"]
    target_delivery = next(d for d in deliveries if d["id"] == del_id)
    assert target_delivery["status"] == "pending"

    # 2. Check History API: must NOT return "confirmed", must match delivery status "pending"
    hist_resp = client.get(f"/api/v1/delivery/{del_id}/history", headers=headers)
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()["data"]
    assert len(hist_data) >= 1
    assert hist_data[0]["status"] == target_delivery["status"]
    assert hist_data[0]["status"] == "pending"
    assert "confirmed" not in [h["status"] for h in hist_data]




