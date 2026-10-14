import uuid
from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_tenant_client(prefix: str):
    """Helper to register and login a distinct tenant."""
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    data = reg_resp.json()
    tenant_id = data["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
        "slug": slug,
    }


@pytest.fixture
def tenant():
    return create_tenant_client("cpn-tenant")


@pytest.fixture
def other_tenant():
    return create_tenant_client("cpn-other")


# ==============================================================================
# 1. VALID COUPON CREATION
# ==============================================================================

def test_valid_coupon_creation(tenant):
    """Test valid percentage and fixed coupon creation with HTTP 201."""
    today = date.today()
    future = today + timedelta(days=30)

    # 1. Percentage coupon
    payload_pct = {
        "code": "WELCOME10",
        "description": "Welcome 10% discount for new customers",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "maximum_discount": 100.0,
        "usage_limit": 100,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }
    resp = client.post("/api/v1/coupons", json=payload_pct, headers=tenant["headers"])
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["code"] == "WELCOME10"
    assert data["discount_type"] == "percentage"
    assert float(data["discount_value"]) == 10.0
    assert data["is_active"] is True
    assert data["usage_limit"] == 100
    assert data["used_count"] == 0

    # 2. Fixed discount coupon
    payload_fixed = {
        "code": "FLAT50A",
        "description": "Flat 50 discount on orders",
        "discount_type": "fixed",
        "discount_value": 50.0,
        "minimum_order_amount": 1.00,
        "maximum_discount": None,
        "usage_limit": 50,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }
    resp_fix = client.post("/api/v1/coupons", json=payload_fixed, headers=tenant["headers"])
    assert resp_fix.status_code == 201, resp_fix.text
    assert resp_fix.json()["code"] == "FLAT50A"
    assert float(resp_fix.json()["discount_value"]) == 50.0


# ==============================================================================
# 2. FUTURE START DATE PREVENTS APPLYING EARLY
# ==============================================================================

def test_future_start_date_prevents_applying_early(tenant):
    """A coupon starting tomorrow cannot be applied today, even if is_active=True."""
    tomorrow = date.today() + timedelta(days=1)
    future = tomorrow + timedelta(days=30)

    payload = {
        "code": "FUTURE10",
        "description": "Future campaign discount",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 10,
        "start_date": tomorrow.isoformat(),
        "end_date": future.isoformat(),
    }
    create_resp = client.post("/api/v1/coupons", json=payload, headers=tenant["headers"])
    assert create_resp.status_code == 201, create_resp.text
    assert create_resp.json()["is_active"] is True

    # Try applying today
    apply_resp = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "FUTURE10", "order_amount": 100.0},
        headers=tenant["headers"],
    )
    assert apply_resp.status_code == 400
    assert "Coupon is not active yet" in apply_resp.text


# ==============================================================================
# 3. DATE ORDER VALIDATION
# ==============================================================================

def test_end_date_before_start_date_rejected(tenant):
    """End date before start date must be rejected with HTTP 422."""
    today = date.today()
    past = today - timedelta(days=5)

    payload = {
        "code": "DATEERR1",
        "description": "Invalid date range test",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 10,
        "start_date": today.isoformat(),
        "end_date": past.isoformat(),
    }
    resp = client.post("/api/v1/coupons", json=payload, headers=tenant["headers"])
    assert resp.status_code == 422
    assert "end date" in resp.text.lower()


# ==============================================================================
# 4. INVALID AND IMPOSSIBLE DATES REJECTED
# ==============================================================================

def test_invalid_and_impossible_dates_rejected(tenant):
    """Impossible dates like 2026-13-40 or 2026-02-30 must return HTTP 422."""
    base_payload = {
        "code": "IMP10",
        "description": "Impossible date test",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 10,
    }

    # Month 13, day 40
    p1 = {**base_payload, "start_date": "2026-13-40", "end_date": "2026-13-45"}
    assert client.post("/api/v1/coupons", json=p1, headers=tenant["headers"]).status_code == 422

    # February 30
    p2 = {**base_payload, "start_date": "2026-02-30", "end_date": "2026-02-30"}
    assert client.post("/api/v1/coupons", json=p2, headers=tenant["headers"]).status_code == 422

    # Boolean as date
    p3 = {**base_payload, "start_date": True, "end_date": "2026-12-31"}
    assert client.post("/api/v1/coupons", json=p3, headers=tenant["headers"]).status_code == 422

    # Empty / whitespace date
    p4 = {**base_payload, "start_date": "   ", "end_date": "2026-12-31"}
    assert client.post("/api/v1/coupons", json=p4, headers=tenant["headers"]).status_code == 422


# ==============================================================================
# 5. VALID ALPHANUMERIC COUPON CODES ACCEPTED (LETTERS + DIGITS)
# ==============================================================================

def test_valid_alphanumeric_codes_accepted(tenant):
    """Codes containing BOTH letters and digits must be accepted."""
    today = date.today()
    future = today + timedelta(days=10)

    for valid_code in ["FESTIVS2026", "DIWALI10", "SAVE20", "ABCD1234"]:
        payload = {
            "code": valid_code,
            "description": f"Valid code test for {valid_code}",
            "discount_type": "fixed",
            "discount_value": 15.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 5,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        }
        resp = client.post("/api/v1/coupons", json=payload, headers=tenant["headers"])
        assert resp.status_code == 201, f"Failed for code: {valid_code}, text: {resp.text}"
        assert resp.json()["code"] == valid_code.upper()


# ==============================================================================
# 6. NUMERIC-ONLY, LETTER-ONLY, AND PUNCTUATION/PLACEHOLDER CODES REJECTED
# ==============================================================================

def test_punctuation_and_placeholder_codes_rejected(tenant):
    """Numeric-only, letter-only, punctuation, placeholders, and whitespace codes must be rejected with HTTP 422."""
    today = date.today()
    future = today + timedelta(days=10)
    base = {
        "description": "Invalid code test",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    disallowed = [
        # Numeric-only
        "12345",
        "1234",
        "1000",
        # Letter-only
        "WELCOME",
        "DIWALI",
        "SAVE",
        # Punctuation & random
        "!@##$%%",
        "----",
        ",,,",
        "+++",
        "|||",
        "///",
        "..",
        ";;;",
        "]]][[",
        "(())",
        # Placeholders
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "dummy",
        # Spaces
        "SPACES IN CODE",
        "SP10 ACES",
    ]

    for bad_code in disallowed:
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "code": bad_code},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid code: {bad_code}"


# ==============================================================================
# 7. VALID DESCRIPTIONS ACCEPTED
# ==============================================================================

def test_valid_descriptions_accepted(tenant):
    """Legitimate human-readable descriptions must be accepted."""
    today = date.today()
    future = today + timedelta(days=10)

    valid_descriptions = [
        "Welcome discount for new customers",
        "Save 10% on your next order!",
        "Discount for purchases above 500",
        "Special Festive Offer (Diwali 2026)",
    ]

    for idx, desc in enumerate(valid_descriptions):
        resp = client.post(
            "/api/v1/coupons",
            json={
                "code": f"VDESC{idx}A",
                "description": desc,
                "discount_type": "percentage",
                "discount_value": 10.0,
                "minimum_order_amount": 50.0,
                "usage_limit": 10,
                "start_date": today.isoformat(),
                "end_date": future.isoformat(),
            },
            headers=tenant["headers"],
        )
        assert resp.status_code == 201, f"Failed on description: {desc}"


# ==============================================================================
# 8. INVALID DESCRIPTIONS REJECTED
# ==============================================================================

def test_invalid_descriptions_rejected(tenant):
    """Numbers-only, punctuation-only, placeholders, and whitespace descriptions must be rejected."""
    today = date.today()
    future = today + timedelta(days=10)
    base = {
        "code": "DESC10A",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    invalid_descriptions = [
        "12345",
        "----",
        "!@##$%%",
        "string",
        "null",
        "none",
        "undefined",
        "test",
        "   ",
        "",
    ]

    for idx, bad_desc in enumerate(invalid_descriptions):
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "code": f"DERR{idx}A", "description": bad_desc},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid description: {bad_desc}"


# ==============================================================================
# 9. DISCOUNT TYPE VALIDATION
# ==============================================================================

def test_discount_type_validation(tenant):
    """Discount type must only accept 'percentage' or 'fixed'."""
    today = date.today()
    future = today + timedelta(days=10)
    base = {
        "code": "DISC10A",
        "description": "Discount type test",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    for invalid_type in ["random", "tiered", "bogo", "123", "", None]:
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "discount_type": invalid_type},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid discount_type: {invalid_type}"
        assert "percentage" in resp.text.lower() and "fixed" in resp.text.lower()


# ==============================================================================
# 10. DISCOUNT VALUE VALIDATION & PRECISION
# ==============================================================================

def test_discount_value_validation(tenant):
    """Discount value validation: For percentage, enforce >= 1 and <= 100, rejecting <1 (0.10, 0.50, 0.99) on create and update. Keep fixed separate."""
    today = date.today()
    future = today + timedelta(days=10)
    base_pct = {
        "code": "VAL10A",
        "description": "Discount value test",
        "discount_type": "percentage",
        "minimum_order_amount": 50.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    # 1. Percentage create rejections: 0, negatives, fractional percentages < 1 (0.10, 0.50, 0.99), >100, booleans, invalid scale
    invalid_pct_values = [
        0,
        -10,
        -0.01,
        0.10,
        0.50,
        0.99,
        0.001,
        0.0001,
        True,
        False,
        100.5,
        150,
        "not_a_number",
    ]

    for idx, bad_val in enumerate(invalid_pct_values):
        resp = client.post(
            "/api/v1/coupons",
            json={**base_pct, "code": f"VERR{idx}A", "discount_value": bad_val},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid percentage discount_value on create: {bad_val}"

    # 2. Percentage create acceptances: 1, 1.5, 10, 99.99, 100
    valid_pct_cases = [
        ("PCTVAL1", 1),
        ("PCTVAL15", 1.5),
        ("PCTVAL10", 10),
        ("PCTVAL99", 99.99),
        ("PCTVAL100", 100),
    ]
    pct_coupon_id = None
    for code, valid_val in valid_pct_cases:
        resp = client.post(
            "/api/v1/coupons",
            json={**base_pct, "code": code, "discount_value": valid_val},
            headers=tenant["headers"],
        )
        assert resp.status_code == 201, f"Failed for valid percentage discount_value {valid_val}: {resp.text}"
        if code == "PCTVAL1":
            pct_coupon_id = resp.json()["id"]

    # 3. Percentage update rejections on existing percentage coupon (<1, >100, 0, negatives)
    assert pct_coupon_id is not None
    for bad_update_val in [0, -5, 0.10, 0.50, 0.99, 100.5, 150]:
        patch_resp = client.patch(
            f"/api/v1/coupons/{pct_coupon_id}",
            json={"discount_value": bad_update_val},
            headers=tenant["headers"],
        )
        assert patch_resp.status_code == 422, f"Allowed invalid percentage discount_value on update: {bad_update_val}"

    # 4. Percentage update acceptances: 1.5, 10, 25.5
    for valid_update_val in [1.5, 10, 25.5]:
        patch_resp = client.patch(
            f"/api/v1/coupons/{pct_coupon_id}",
            json={"discount_value": valid_update_val},
            headers=tenant["headers"],
        )
        assert patch_resp.status_code == 200, f"Failed for valid percentage update: {valid_update_val}"
        assert float(patch_resp.json()["discount_value"]) == float(valid_update_val)

    # 5. Fixed-amount validation kept separate: rejects 0 and negative, accepts fractional amounts like 0.50
    base_fix = {
        "code": "FIXVAL01",
        "description": "Fixed discount test",
        "discount_type": "fixed",
        "minimum_order_amount": 50.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }
    # Reject 0 and negative for fixed
    for bad_fix in [0, -10]:
        resp_bad_fix = client.post(
            "/api/v1/coupons",
            json={**base_fix, "code": "FIXBAD01", "discount_value": bad_fix},
            headers=tenant["headers"],
        )
        assert resp_bad_fix.status_code == 422

    # Accept fractional fixed discount (e.g. 0.50, 0.99, 1.00)
    resp_fix_frac = client.post(
        "/api/v1/coupons",
        json={**base_fix, "code": "FIXFRAC1", "discount_value": 0.50},
        headers=tenant["headers"],
    )
    assert resp_fix_frac.status_code == 201, resp_fix_frac.text
    fix_id = resp_fix_frac.json()["id"]

    # Update fixed coupon to another fractional value (0.99)
    resp_fix_patch = client.patch(
        f"/api/v1/coupons/{fix_id}",
        json={"discount_value": 0.99},
        headers=tenant["headers"],
    )
    assert resp_fix_patch.status_code == 200
    assert float(resp_fix_patch.json()["discount_value"]) == 0.99


# ==============================================================================
# 11. MAXIMUM DISCOUNT VALIDATION
# ==============================================================================

def test_maximum_discount_validation(tenant):
    """Maximum discount, when provided, must be >= 1.00. Rejects 0, negative, 0.10, 0.50, and <1.00 on create and update."""
    today = date.today()
    future = today + timedelta(days=10)
    base = {
        "code": "MAX10A",
        "description": "Max discount test",
        "discount_type": "percentage",
        "discount_value": 20.0,
        "minimum_order_amount": 50.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    # 1. Reject invalid maximum_discount values on create (< 1.00, 0, negative, booleans, invalid scale)
    invalid_max = [
        0,
        -5,
        -0.01,
        0.10,
        0.50,
        0.99,
        0.0001,
        0.001,
        True,
        "arbitrary_string",
    ]

    for idx, bad_max in enumerate(invalid_max):
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "code": f"MDERR{idx}A", "maximum_discount": bad_max},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid maximum_discount on create: {bad_max}"

    # 2. Accept >= 1.00 on create (1.00, 1.50, 10.25, None)
    valid_max_cases = [
        ("MDVAL100", 1.00),
        ("MDVAL150", 1.50),
        ("MDVAL1025", 10.25),
        ("MDVALNON0", None),
    ]
    created_coupon_id = None
    for code, max_val in valid_max_cases:
        payload = {**base, "code": code}
        if max_val is not None:
            payload["maximum_discount"] = max_val
        resp = client.post("/api/v1/coupons", json=payload, headers=tenant["headers"])
        assert resp.status_code == 201, f"Failed for valid maximum_discount: {max_val}, response: {resp.text}"
        if max_val == 1.00:
            created_coupon_id = resp.json()["id"]

    # 3. Reject invalid maximum_discount on update (< 1.00, 0, negative)
    assert created_coupon_id is not None
    for bad_update_max in [0, -1, 0.10, 0.50, 0.99]:
        patch_resp = client.patch(
            f"/api/v1/coupons/{created_coupon_id}",
            json={"maximum_discount": bad_update_max},
            headers=tenant["headers"],
        )
        assert patch_resp.status_code == 422, f"Allowed invalid maximum_discount on update: {bad_update_max}"

    # 4. Accept valid maximum_discount on update (1.00, 1.50, 10.25)
    for valid_update_max in [1.00, 1.50, 10.25]:
        patch_resp = client.patch(
            f"/api/v1/coupons/{created_coupon_id}",
            json={"maximum_discount": valid_update_max},
            headers=tenant["headers"],
        )
        assert patch_resp.status_code == 200, f"Failed for valid update maximum_discount: {valid_update_max}"
        assert float(patch_resp.json()["maximum_discount"]) == float(valid_update_max)


# ==============================================================================
# 12. MINIMUM ORDER AMOUNT VALIDATION (CREATE AND UPDATE)
# ==============================================================================

def test_minimum_order_amount_validation(tenant):
    """Minimum order amount must be >= 1.00. Rejects 0, negative, 0.10, 0.50, <1.00 on create and update."""
    today = date.today()
    future = today + timedelta(days=10)
    base = {
        "code": "MOA10A",
        "description": "Min order test",
        "discount_type": "fixed",
        "discount_value": 10.0,
        "usage_limit": 5,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    # 1. Reject invalid minimum_order_amount on create (0, negative, 0.10, 0.50, 0.99, booleans, scale violations)
    invalid_moa = [
        0,
        0.00,
        -10,
        -0.01,
        0.10,
        0.50,
        0.99,
        0.001,
        0.0001,
        True,
        False,
        "invalid_text",
    ]

    for idx, bad_moa in enumerate(invalid_moa):
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "code": f"MOAERR{idx}A", "minimum_order_amount": bad_moa},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid minimum_order_amount on create: {bad_moa}"

    # 2. Accept >= 1.00 on create (1.00, 1.50, 10.25)
    valid_moa_cases = [
        ("MOAVAL100", 1.00),
        ("MOAVAL150", 1.50),
        ("MOAVAL1025", 10.25),
    ]
    created_coupon_id = None
    for code, moa_val in valid_moa_cases:
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "code": code, "minimum_order_amount": moa_val},
            headers=tenant["headers"],
        )
        assert resp.status_code == 201, f"Failed for valid minimum_order_amount: {moa_val}, response: {resp.text}"
        if moa_val == 1.00:
            created_coupon_id = resp.json()["id"]

    # 3. Reject invalid minimum_order_amount on update (< 1.00, 0, negative)
    assert created_coupon_id is not None
    for bad_update_moa in [0, -1, 0.10, 0.50, 0.99]:
        patch_resp = client.patch(
            f"/api/v1/coupons/{created_coupon_id}",
            json={"minimum_order_amount": bad_update_moa},
            headers=tenant["headers"],
        )
        assert patch_resp.status_code == 422, f"Allowed invalid minimum_order_amount on update: {bad_update_moa}"

    # 4. Accept valid minimum_order_amount on update (1.00, 1.50, 10.25)
    for valid_update_moa in [1.00, 1.50, 10.25]:
        patch_resp = client.patch(
            f"/api/v1/coupons/{created_coupon_id}",
            json={"minimum_order_amount": valid_update_moa},
            headers=tenant["headers"],
        )
        assert patch_resp.status_code == 200, f"Failed for valid update minimum_order_amount: {valid_update_moa}"
        assert float(patch_resp.json()["minimum_order_amount"]) == float(valid_update_moa)


def test_minimum_order_amount_threshold_and_boundary(tenant):
    """Verify that minimum_order_amount = 1.00 is enforced during application, rejecting below and accepting at/above."""
    today = date.today()
    future = today + timedelta(days=10)

    # 1. 0.10 and 0.50 are rejected on creation
    for rejected_val in [0.10, 0.50]:
        bad_resp = client.post(
            "/api/v1/coupons",
            json={
                "code": "REJMIN01",
                "description": "Rejected minimum order coupon",
                "discount_type": "percentage",
                "discount_value": 10.0,
                "minimum_order_amount": rejected_val,
                "usage_limit": 10,
                "start_date": today.isoformat(),
                "end_date": future.isoformat(),
            },
            headers=tenant["headers"],
        )
        assert bad_resp.status_code == 422

    # 2. Create coupon with minimum_order_amount = 1.00
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "MINONE01",
            "description": "Coupon with 1.00 minimum order",
            "discount_type": "percentage",
            "discount_value": 10.0,
            "minimum_order_amount": 1.00,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201, create_resp.text
    assert float(create_resp.json()["minimum_order_amount"]) == 1.00

    # 3. Order below threshold (order_amount = 0.50 < 1.00) -> Rejected with HTTP 400
    resp_below = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "MINONE01", "order_amount": 0.50},
        headers=tenant["headers"],
    )
    assert resp_below.status_code == 400
    assert "minimum order amount" in resp_below.text.lower()

    # 4. Order exactly at threshold (order_amount = 1.00) -> Accepted
    resp_exact = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "MINONE01", "order_amount": 1.00},
        headers=tenant["headers"],
    )
    assert resp_exact.status_code == 200, resp_exact.text
    assert resp_exact.json()["original_amount"] == 1.00
    assert resp_exact.json()["discount_amount"] == 0.10
    assert resp_exact.json()["final_amount"] == 0.90

    # 5. Order above threshold (order_amount = 1.50) -> Accepted
    resp_above = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "MINONE01", "order_amount": 1.50},
        headers=tenant["headers"],
    )
    assert resp_above.status_code == 200, resp_above.text
    assert resp_above.json()["original_amount"] == 1.50
    assert resp_above.json()["discount_amount"] == 0.15
    assert resp_above.json()["final_amount"] == 1.35

    # 6. Order with decimal (order_amount = 10.25) -> Accepted
    resp_dec = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "MINONE01", "order_amount": 10.25},
        headers=tenant["headers"],
    )
    assert resp_dec.status_code == 200, resp_dec.text
    assert resp_dec.json()["original_amount"] == 10.25
    assert resp_dec.json()["discount_amount"] == 1.02
    assert resp_dec.json()["final_amount"] == 9.22


# ==============================================================================
# 13. USAGE LIMIT VALIDATION
# ==============================================================================

def test_usage_limit_validation(tenant):
    """Usage limit must reject 0, negative values, decimals (0.5), booleans (True), and strings."""
    today = date.today()
    future = today + timedelta(days=10)
    base = {
        "code": "ULIM10A",
        "description": "Usage limit test",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "minimum_order_amount": 50.0,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    invalid_limits = [
        0,
        -1,
        0.5,
        1.5,
        True,
        False,
        "10",
        "arbitrary",
    ]

    for idx, bad_limit in enumerate(invalid_limits):
        resp = client.post(
            "/api/v1/coupons",
            json={**base, "code": f"ULERR{idx}A", "usage_limit": bad_limit},
            headers=tenant["headers"],
        )
        assert resp.status_code == 422, f"Allowed invalid usage_limit: {bad_limit}"


# ==============================================================================
# 14. IS_ACTIVE STRICT BOOLEAN VALIDATION
# ==============================================================================

def test_is_active_strict_boolean_validation(tenant):
    """is_active must strictly accept JSON booleans (true, false) and reject strings/numbers."""
    # Create coupon to patch
    today = date.today()
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "STATUS10A",
            "description": "Status test coupon",
            "discount_type": "fixed",
            "discount_value": 10.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=10)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    # Valid boolean updates
    resp_false = client.patch(
        f"/api/v1/coupons/{coupon_id}/status",
        json={"is_active": False},
        headers=tenant["headers"],
    )
    assert resp_false.status_code == 200
    assert resp_false.json()["is_active"] is False

    resp_true = client.patch(
        f"/api/v1/coupons/{coupon_id}/status",
        json={"is_active": True},
        headers=tenant["headers"],
    )
    assert resp_true.status_code == 200
    assert resp_true.json()["is_active"] is True

    # Invalid non-boolean types rejected with 422
    for bad_bool in ["true", "false", "yes", "no", 1, 0, "active"]:
        resp_bad = client.patch(
            f"/api/v1/coupons/{coupon_id}/status",
            json={"is_active": bad_bool},
            headers=tenant["headers"],
        )
        assert resp_bad.status_code == 422, f"Allowed non-boolean is_active: {bad_bool}"
        assert "expected a boolean" in resp_bad.text.lower()


# ==============================================================================
# 15. UPDATE ONGOING COUPON PRESERVES VALIDITY
# ==============================================================================

def test_update_ongoing_coupon_preserves_validity(tenant):
    """Updating an ongoing coupon whose unchanged start_date is today or earlier must succeed."""
    today = date.today()
    future = today + timedelta(days=10)

    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "ONGOING01",
            "description": "Ongoing coupon test",
            "discount_type": "fixed",
            "discount_value": 20.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    # Partial update: edit description only, omit start_date
    update_resp = client.patch(
        f"/api/v1/coupons/{coupon_id}",
        json={"description": "Updated description for ongoing coupon"},
        headers=tenant["headers"],
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["description"] == "Updated description for ongoing coupon"


# ==============================================================================
# 16. APPLY COUPON RETURNS NUMERIC AMOUNTS IN JSON
# ==============================================================================

def test_apply_coupon_returns_numeric_amounts(tenant):
    """POST /coupons/apply must return original_amount, discount_amount, final_amount as unquoted numbers and non-negative."""
    today = date.today()
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "NUMERIC10",
            "description": "Numeric serialization test",
            "discount_type": "percentage",
            "discount_value": 10.0,
            "minimum_order_amount": 50.0,
            "maximum_discount": 20.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=10)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201

    apply_resp = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "NUMERIC10", "order_amount": 100.00},
        headers=tenant["headers"],
    )
    assert apply_resp.status_code == 200, apply_resp.text
    data = apply_resp.json()

    # 1. Verify types in parsed JSON response are numeric, not strings
    assert isinstance(data["original_amount"], (int, float))
    assert isinstance(data["discount_amount"], (int, float))
    assert isinstance(data["final_amount"], (int, float))
    assert not isinstance(data["original_amount"], str)
    assert not isinstance(data["discount_amount"], str)
    assert not isinstance(data["final_amount"], str)
    assert data["original_amount"] == 100.0
    assert data["discount_amount"] == 10.0
    assert data["final_amount"] == 90.0

    # 2. Verify raw text contains raw numbers without string quotes
    raw_text = apply_resp.text
    assert '"original_amount":100' in raw_text or '"original_amount": 100' in raw_text
    assert '"discount_amount":10' in raw_text or '"discount_amount": 10' in raw_text
    assert '"final_amount":90' in raw_text or '"final_amount": 90' in raw_text
    assert '"original_amount":"100' not in raw_text
    assert '"discount_amount":"10' not in raw_text
    assert '"final_amount":"90' not in raw_text

    # 3. Create flat discount coupon to test non-negative final_amount boundary
    flat_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "FLAT100A",
            "description": "Flat 100 discount",
            "discount_type": "fixed",
            "discount_value": 100.0,
            "minimum_order_amount": 10.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=10)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert flat_resp.status_code == 201

    # Order of 50 with flat discount 100 -> discount capped at order_amount, final_amount == 0.0 (never negative)
    zero_apply = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "FLAT100A", "order_amount": 50.0},
        headers=tenant["headers"],
    )
    assert zero_apply.status_code == 200, zero_apply.text
    zero_data = zero_apply.json()
    assert zero_data["original_amount"] == 50.0
    assert zero_data["discount_amount"] == 50.0
    assert zero_data["final_amount"] == 0.0
    assert zero_data["final_amount"] >= 0.0
    assert isinstance(zero_data["final_amount"], (int, float))
    assert not isinstance(zero_data["final_amount"], str)

    # 4. Verify OpenAPI schema reflects numeric types (number, not string)
    openapi_schema = app.openapi()
    apply_schema = openapi_schema["components"]["schemas"]["ApplyCouponResponse"]
    assert apply_schema["properties"]["original_amount"]["type"] == "number"
    assert apply_schema["properties"]["discount_amount"]["type"] == "number"
    assert apply_schema["properties"]["final_amount"]["type"] == "number"


# ==============================================================================
# 17. APPLY COUPON REJECTS EXPIRED, INACTIVE, AND LIMIT BREACHES
# ==============================================================================

def test_apply_coupon_rejections(tenant):
    """Apply coupon rejects inactive, below-minimum, and exhausted coupons."""
    today = date.today()
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "REJECT10A",
            "description": "Coupon rejection test",
            "discount_type": "fixed",
            "discount_value": 20.0,
            "minimum_order_amount": 100.0,
            "usage_limit": 1,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=5)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    # 1. Order below minimum order amount
    resp_min = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "REJECT10A", "order_amount": 50.0},
        headers=tenant["headers"],
    )
    assert resp_min.status_code == 400
    assert "minimum order amount" in resp_min.text.lower()

    # 2. Deactivate coupon
    client.patch(
        f"/api/v1/coupons/{coupon_id}/status",
        json={"is_active": False},
        headers=tenant["headers"],
    )
    resp_inact = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "REJECT10A", "order_amount": 150.0},
        headers=tenant["headers"],
    )
    assert resp_inact.status_code == 400
    assert "inactive" in resp_inact.text.lower()


# ==============================================================================
# 18. MALFORMED JSON STATUS UPDATE RETURNS 422
# ==============================================================================

def test_malformed_json_status_update_returns_422(tenant):
    """Raw body `{"is_active": yes}` returns HTTP 422 with boolean format message, not 500."""
    today = date.today()
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "JSON10A",
            "description": "Malformed JSON test",
            "discount_type": "fixed",
            "discount_value": 10.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 5,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=5)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    raw_malformed_body = b'{"is_active": yes}'
    resp = client.patch(
        f"/api/v1/coupons/{coupon_id}/status",
        content=raw_malformed_body,
        headers={**tenant["headers"], "Content-Type": "application/json"},
    )
    assert resp.status_code == 422
    assert "expected a boolean: true or false" in resp.text.lower()


# ==============================================================================
# 19. GET ENDPOINTS NO-DATA PRESERVES CONTRACT (ALTERNATIVE B)
# ==============================================================================

def test_get_endpoints_no_data_preserves_contract(other_tenant):
    """A fresh tenant with 0 coupons returns HTTP 404 with structured error message, never empty body or bare null."""
    resp_list = client.get("/api/v1/coupons", headers=other_tenant["headers"])
    assert resp_list.status_code == 404
    data_list = resp_list.json()
    assert data_list["success"] is False
    assert "no coupons found" in data_list["message"].lower()

    resp_act = client.get("/api/v1/coupons/active", headers=other_tenant["headers"])
    assert resp_act.status_code == 404
    assert "no active coupons found" in resp_act.json()["message"].lower()

    resp_exp = client.get("/api/v1/coupons/expired", headers=other_tenant["headers"])
    assert resp_exp.status_code == 404
    assert "no expired coupons found" in resp_exp.json()["message"].lower()

    # Stats endpoint returns valid 200 with 0 counts
    resp_stats = client.get("/api/v1/coupons/stats", headers=other_tenant["headers"])
    assert resp_stats.status_code == 200
    assert resp_stats.json()["total_coupons"] == 0


# ==============================================================================
# 20. MISSING INDIVIDUAL COUPON RETURNS 404
# ==============================================================================

def test_missing_individual_coupon_returns_404(tenant):
    """GET /coupons/{id} for non-existent coupon returns HTTP 404."""
    resp = client.get("/api/v1/coupons/999999", headers=tenant["headers"])
    assert resp.status_code == 404
    assert "coupon not found" in resp.text.lower()


# ==============================================================================
# 21. TENANT ISOLATION PRESERVED
# ==============================================================================

def test_tenant_isolation_preserved(tenant, other_tenant):
    """Tenant B cannot view, update, delete, or apply Tenant A's coupon."""
    today = date.today()
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "TENANT10A",
            "description": "Tenant A exclusive coupon",
            "discount_type": "fixed",
            "discount_value": 25.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=10)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    # Tenant B tries to GET coupon by ID -> 404
    assert client.get(f"/api/v1/coupons/{coupon_id}", headers=other_tenant["headers"]).status_code == 404

    # Tenant B tries to PATCH status -> 404
    assert client.patch(
        f"/api/v1/coupons/{coupon_id}/status",
        json={"is_active": False},
        headers=other_tenant["headers"],
    ).status_code == 404

    # Tenant B tries to apply Tenant A's coupon code -> 404
    apply_resp = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "TENANT10A", "order_amount": 100.0},
        headers=other_tenant["headers"],
    )
    assert apply_resp.status_code == 404

    # Tenant B CAN create the SAME code in their own tenant scope
    create_other = client.post(
        "/api/v1/coupons",
        json={
            "code": "TENANT10A",
            "description": "Tenant B version of code",
            "discount_type": "percentage",
            "discount_value": 15.0,
            "minimum_order_amount": 40.0,
            "usage_limit": 5,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=10)).isoformat(),
        },
        headers=other_tenant["headers"],
    )
    assert create_other.status_code == 201

    # Tenant A creating duplicate within same tenant -> 409
    dup_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "TENANT10A",
            "description": "Duplicate in tenant A",
            "discount_type": "fixed",
            "discount_value": 10.0,
            "minimum_order_amount": 20.0,
            "usage_limit": 5,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=10)).isoformat(),
        },
        headers=tenant["headers"],
    )
    assert dup_resp.status_code == 409


# ==============================================================================
# 22. END-TO-END VALID COUPON LIFECYCLE
# ==============================================================================

def test_end_to_end_coupon_lifecycle(tenant):
    """Full lifecycle: create -> list -> validate -> apply -> patch status -> patch details -> delete."""
    today = date.today()
    future = today + timedelta(days=20)

    # 1. Create
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "LIFECYCLE20",
            "description": "Full lifecycle coupon test",
            "discount_type": "percentage",
            "discount_value": 20.0,
            "minimum_order_amount": 100.0,
            "maximum_discount": 50.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    # 2. List
    list_resp = client.get("/api/v1/coupons", headers=tenant["headers"])
    assert list_resp.status_code == 200
    assert any(c["id"] == coupon_id for c in list_resp.json())

    # 3. Validate
    val_resp = client.post(
        "/api/v1/coupons/validate",
        json={"coupon_code": "LIFECYCLE20", "order_amount": 200.0},
        headers=tenant["headers"],
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True

    # 4. Apply
    apply_resp = client.post(
        "/api/v1/coupons/apply",
        json={"coupon_code": "LIFECYCLE20", "order_amount": 200.0},
        headers=tenant["headers"],
    )
    assert apply_resp.status_code == 200
    app_data = apply_resp.json()
    assert app_data["discount_amount"] == 40.0
    assert app_data["final_amount"] == 160.0

    # 5. Patch status (deactivate)
    status_resp = client.patch(
        f"/api/v1/coupons/{coupon_id}/status",
        json={"is_active": False},
        headers=tenant["headers"],
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["is_active"] is False

    # 6. Patch details
    patch_resp = client.patch(
        f"/api/v1/coupons/{coupon_id}",
        json={"description": "Updated lifecycle description", "usage_limit": 15},
        headers=tenant["headers"],
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated lifecycle description"
    assert patch_resp.json()["usage_limit"] == 15

    # 7. Delete
    del_resp = client.delete(f"/api/v1/coupons/{coupon_id}", headers=tenant["headers"])
    assert del_resp.status_code == 200

    # 8. Confirm deleted
    assert client.get(f"/api/v1/coupons/{coupon_id}", headers=tenant["headers"]).status_code == 404
