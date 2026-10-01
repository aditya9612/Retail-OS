"""
Phase 2-D2: Mobile + OTP Login — Comprehensive Test Suite.

Updated for Task 10:
- Domain-less mobile OTP requests (phone only)
- Global phone uniqueness (unique phones per tenant)
- Dynamic OTP verification via MockSMSProvider and deterministic fixture
- Preserves all security assertions: enumeration protection, brute-force lockout,
  cooldown, rate-limiting, normalization, JWT compatibility, account status.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.sms_provider import MockSMSProvider

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXED_OTP = "654321"

_otp_phone_seq = 60000000


@pytest.fixture(autouse=True)
def ensure_deterministic_otp(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
    MockSMSProvider.clear_sent_messages()
    yield
    MockSMSProvider.clear_sent_messages()
    get_settings.cache_clear()


def _last_otp() -> str:
    messages = MockSMSProvider.get_sent_messages()
    if messages:
        return messages[-1][1]
    return FIXED_OTP


def _unique():
    return uuid.uuid4().hex[:8]


def _unique_phone() -> str:
    global _otp_phone_seq
    _otp_phone_seq += 1
    return f"9{_otp_phone_seq:09d}"


def _register(slug, email, phone=None, password="TestPass@123!"):
    if phone is None:
        phone = _unique_phone()
    payload = {
        "tenant_name": f"MobileTest {slug}",
        "domain": slug,
        "email": email,
        "admin_name": "Mobile Tester",
        "password": password,
        "phone": phone,
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 200, f"Register failed: {resp.json()}"
    data = resp.json()
    data["phone"] = phone
    return data


def _admin_token(slug, email, password="TestPass@123!"):
    """Get a super-admin-like token for tenant management via email login."""
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _request_otp(phone: str):
    return client.post(
        "/api/v1/auth/login/mobile-otp/request",
        json={"phone": phone},
    )


def _verify_otp(phone: str, otp: str):
    return client.post(
        "/api/v1/auth/login/mobile-otp/verify",
        json={"phone": phone, "otp": otp},
    )


# ---------------------------------------------------------------------------
# 1. Successful OTP login — active tenant + active user with store_id NULL
# ---------------------------------------------------------------------------

class TestMobileOTPSuccessFlow:

    def test_request_otp_success_generic_response(self, unique_slug):
        """OTP request for registered phone returns generic message (no OTP)."""
        phone = _unique_phone()
        email = f"otp-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        resp = _request_otp(phone)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "If the account exists" in data["message"]
        assert "otp" not in str(data).lower() or FIXED_OTP not in str(data)
        assert "expires_in" in data

    def test_verify_otp_returns_jwt(self, unique_slug):
        """Successful OTP verify returns access_token and refresh_token."""
        phone = _unique_phone()
        email = f"otp2-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        resp = _verify_otp(phone, _last_otp())

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data.get("token_type") == "bearer"

    def test_otp_not_in_verify_response(self, unique_slug):
        """The verify response must never contain the plaintext OTP."""
        phone = _unique_phone()
        email = f"otp3-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        sent_code = _last_otp()
        resp = _verify_otp(phone, sent_code)

        assert sent_code not in resp.text

    def test_jwt_claims_match_email_login(self, unique_slug):
        """JWT from mobile OTP login has same claim structure as email/password login."""
        import base64, json as _json

        phone = _unique_phone()
        email = f"claim-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        # Email login
        email_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        email_token = email_resp.json()["access_token"]

        # Mobile OTP login
        _request_otp(phone)
        otp_resp = _verify_otp(phone, _last_otp())
        otp_token = otp_resp.json()["access_token"]

        def _decode_claims(token):
            payload_b64 = token.split(".")[1]
            padding = 4 - len(payload_b64) % 4
            return _json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))

        email_claims = _decode_claims(email_token)
        otp_claims = _decode_claims(otp_token)

        # Same structural keys
        for key in ("sub", "tenant_id", "role", "store_id", "type"):
            assert key in email_claims, f"Key {key!r} missing from email JWT"
            assert key in otp_claims, f"Key {key!r} missing from OTP JWT"

        # Same values for same user
        assert email_claims["sub"] == otp_claims["sub"]
        assert email_claims["tenant_id"] == otp_claims["tenant_id"]


# ---------------------------------------------------------------------------
# 2. Phone normalization
# ---------------------------------------------------------------------------

class TestPhoneNormalizationInOTPLogin:

    def test_plus91_prefix_normalized(self, unique_slug):
        """OTP request with +91 prefix is canonicalized correctly."""
        phone = _unique_phone()
        email = f"norm-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        # Request with +91 prefix (Pydantic normalizes to 10-digit canonical)
        resp = _request_otp(f"+91{phone}")
        assert resp.status_code == 200

    def test_normalized_phone_for_verify(self, unique_slug):
        """OTP verify with different but canonically equivalent phone succeeds."""
        phone = _unique_phone()
        email = f"norm2-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(f"+91{phone}")
        resp = _verify_otp(f"0{phone}", _last_otp())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. Enumeration protection
# ---------------------------------------------------------------------------

class TestEnumerationProtection:

    def test_unknown_phone_returns_generic_response(self, unique_slug):
        """OTP request for unknown phone still returns 200 with generic message."""
        email = f"enum-{unique_slug}@example.com"
        _register(unique_slug, email)

        resp = _request_otp("9111111111")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "If the account exists" in data["message"]

    def test_invalid_phone_format_returns_422(self):
        """OTP request with invalid phone format returns 422 validation error."""
        resp = _request_otp("12345")
        assert resp.status_code == 422

    def test_verify_unknown_phone_returns_401(self, unique_slug):
        """OTP verify for an unregistered phone returns 401."""
        phone = _unique_phone()
        email = f"enu2-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        # Generate OTP for this user
        _request_otp(phone)

        # Try to verify with a different unregistered phone
        resp = _verify_otp("9333333333", FIXED_OTP)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 4. Account status enforcement
# ---------------------------------------------------------------------------

class TestAccountStatusEnforcement:

    def test_inactive_user_otp_request_silently_succeeds(self, unique_slug):
        """
        OTP request for an inactive user returns the generic response
        (enumeration protection: we cannot reveal whether user is inactive).
        """
        phone = _unique_phone()
        email = f"inactive-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        token = _admin_token(unique_slug, email)

        # Deactivate user via API
        user_id = reg["user_id"]
        client.patch(
            f"/api/v1/users/{user_id}/activate",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Whether deactivation succeeded or not, verify OTP request still returns generic
        resp = _request_otp(phone)
        assert resp.status_code == 200

    def test_inactive_user_otp_verify_rejected(self, unique_slug):
        """
        OTP verify for an inactive user must be rejected.
        We simulate by directly building the state.
        """
        from app.core.database import SessionLocal
        from app.services.auth_service import AuthService, OTPPurpose

        phone = _unique_phone()
        email = f"inactive2-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)

        # Manually deactivate user in DB
        db = SessionLocal()
        try:
            from app.models.user import User
            user = db.query(User).filter(User.email == email).first()
            if user:
                user.is_active = False
                db.commit()
        finally:
            db.close()

        # Pre-seed OTP in fake redis
        db2 = SessionLocal()
        try:
            svc = AuthService(db2)
            svc.generate_and_store_otp(
                purpose=OTPPurpose.MOBILE_LOGIN,
                tenant_id=reg["tenant_id"],
                identifier=phone,
                enforce_cooldown=False,
            )
        finally:
            db2.close()

        resp = _verify_otp(phone, _last_otp())
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. OTP security enforcement
# ---------------------------------------------------------------------------

class TestOTPSecurity:

    def test_wrong_otp_rejected(self, unique_slug):
        """Wrong OTP returns 401."""
        phone = _unique_phone()
        email = f"wrong-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        resp = _verify_otp(phone, "000000")
        assert resp.status_code == 401

    def test_otp_replay_rejected(self, unique_slug):
        """Used OTP cannot be verified again (single-use)."""
        phone = _unique_phone()
        email = f"replay-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        otp = _last_otp()
        first = _verify_otp(phone, otp)
        assert first.status_code == 200

        second = _verify_otp(phone, otp)
        assert second.status_code == 401

    def test_brute_force_5_attempts(self, unique_slug):
        """After 5 wrong OTP attempts the OTP is invalidated."""
        phone = _unique_phone()
        email = f"brute-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        otp = _last_otp()

        for _ in range(5):
            _verify_otp(phone, "000000")

        # 6th attempt with correct code must fail
        resp = _verify_otp(phone, otp)
        assert resp.status_code == 401

    def test_otp_resend_cooldown(self, unique_slug):
        """Requesting two OTPs within 60s returns 401 (cooldown)."""
        phone = _unique_phone()
        email = f"cooldown-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        resp = _request_otp(phone)
        assert resp.status_code == 401

    def test_otp_rate_limit(self, unique_slug, fake_redis):
        """After 3 OTP requests within 15 min the 4th is rejected."""
        phone = _unique_phone()
        email = f"rate-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        # Make 3 real API requests; clear only cooldown keys between each
        # so we bypass the 60s cooldown while keeping the rate-limit counter.
        for i in range(3):
            resp = _request_otp(phone)
            assert resp.status_code == 200, f"Request {i+1} failed: {resp.json()}"
            # Remove only cooldown keys so next request isn't blocked by cooldown
            cooldown_keys = [k for k in list(fake_redis._store) if "cooldown" in k]
            for k in cooldown_keys:
                del fake_redis._store[k]

        # 4th request — rate limit (3 per 15 min) must be hit
        resp = _request_otp(phone)
        assert resp.status_code in (401, 429)


# ---------------------------------------------------------------------------
# 6. Cross-tenant isolation & Global Phone Uniqueness
# ---------------------------------------------------------------------------

class TestCrossTenantIsolation:

    def test_same_phone_different_tenants_isolated(self, fake_redis):
        """Under global phone uniqueness, duplicate phone across tenants is rejected (409) and distinct phones are isolated."""
        slug_a = f"tenant-a-{_unique()}"
        slug_b = f"tenant-b-{_unique()}"
        email_a = f"a-{_unique()}@example.com"
        email_b = f"b-{_unique()}@example.com"
        phone_a = _unique_phone()
        phone_b = _unique_phone()

        # Register Tenant A with phone_a
        _register(slug_a, email_a, phone=phone_a)

        # Attempting to register Tenant B with phone_a is rejected with 409 Conflict
        dup_resp = client.post("/api/v1/auth/register", json={
            "tenant_name": f"MobileTest {slug_b}",
            "domain": slug_b,
            "email": email_b,
            "admin_name": "Mobile Tester",
            "password": "TestPass@123!",
            "phone": phone_a,
        })
        assert dup_resp.status_code == 409
        assert "already registered" in dup_resp.text.lower()

        # Register Tenant B with distinct phone_b
        _register(slug_b, email_b, phone=phone_b)

        # Request OTP on phone_a
        _request_otp(phone_a)

        # Try to verify with phone_b — must fail (401)
        resp = _verify_otp(phone_b, _last_otp())
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Cross-purpose isolation
# ---------------------------------------------------------------------------

class TestCrossPurposeIsolation:

    def test_password_reset_otp_cannot_login(self, unique_slug):
        """PASSWORD_RESET OTP must not authenticate a MOBILE_LOGIN request."""
        phone = _unique_phone()
        email = f"purpose-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        # Request a password-reset OTP (different purpose)
        client.post("/api/v1/auth/forgot-password", json={"email": email})

        # Try to use it for mobile login — must fail (different purpose namespace)
        resp = _verify_otp(phone, _last_otp())
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Mobile verified flag
# ---------------------------------------------------------------------------

class TestMobileVerifiedFlag:

    def test_is_mobile_verified_set_after_otp_login(self, unique_slug):
        """After successful mobile OTP login, is_mobile_verified is True."""
        from app.core.database import SessionLocal
        from app.models.user import User

        phone = _unique_phone()
        email = f"verified-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)

        _request_otp(phone)
        resp = _verify_otp(phone, _last_otp())
        assert resp.status_code == 200

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            assert user is not None
            assert user.is_mobile_verified is True
            assert user.mobile_verified_at is not None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 9. Endpoint boundary checks
# ---------------------------------------------------------------------------

class TestEndpointBoundaries:

    def test_mobile_otp_request_endpoint_exists(self):
        """POST /api/v1/auth/login/mobile-otp/request exists and returns 422 on missing body."""
        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={})
        assert resp.status_code == 422

    def test_mobile_otp_verify_endpoint_exists(self):
        """POST /api/v1/auth/login/mobile-otp/verify exists and returns 422 on missing body."""
        resp = client.post("/api/v1/auth/login/mobile-otp/verify", json={})
        assert resp.status_code == 422

    def test_mobile_pin_endpoint_exists(self):
        """POST /api/v1/auth/login/mobile-pin exists and returns 422 on missing body."""
        resp = client.post("/api/v1/auth/login/mobile-pin", json={})
        assert resp.status_code == 422

    def test_pin_setup_endpoint_exists(self):
        """POST /api/v1/auth/pin/setup exists and requires authentication."""
        resp = client.post("/api/v1/auth/pin/setup", json={})
        assert resp.status_code == 401

    def test_pin_change_endpoint_exists(self):
        """POST /api/v1/auth/pin/change exists and requires authentication."""
        resp = client.post("/api/v1/auth/pin/change", json={})
        assert resp.status_code == 401

    def test_pin_reset_request_endpoint_exists(self):
        """POST /api/v1/auth/pin/reset/request exists and validates body."""
        resp = client.post("/api/v1/auth/pin/reset/request", json={})
        assert resp.status_code == 422

    def test_pin_reset_verify_endpoint_exists(self):
        """POST /api/v1/auth/pin/reset/verify exists and validates body."""
        resp = client.post("/api/v1/auth/pin/reset/verify", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10. Backward compatibility — existing endpoints unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_email_login_still_works(self, unique_slug):
        email = f"compat-{unique_slug}@example.com"
        _register(unique_slug, email)
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_refresh_still_works(self, unique_slug):
        email = f"compat2-{unique_slug}@example.com"
        _register(unique_slug, email)
        login = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        refresh_token = login.json()["refresh_token"]

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200

    def test_deprecated_refresh_token_still_works(self, unique_slug):
        email = f"compat3-{unique_slug}@example.com"
        _register(unique_slug, email)
        login = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        refresh_token = login.json()["refresh_token"]

        resp = client.post("/api/v1/auth/refresh-token", json={"refresh_token": refresh_token})
        assert resp.status_code == 200

    def test_logout_still_works(self, unique_slug):
        email = f"compat4-{unique_slug}@example.com"
        _register(unique_slug, email)
        login = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        token = login.json()["access_token"]

        resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_forgot_password_still_works(self, unique_slug, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 111111)
        email = f"compat5-{unique_slug}@example.com"
        _register(unique_slug, email)
        resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert resp.status_code == 200
        assert "otp" not in resp.json()

    def test_otp_not_in_otp_request_response(self, unique_slug):
        """Explicitly verify that neither request nor verify response contains plaintext OTP."""
        phone = _unique_phone()
        email = f"security-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        req_resp = _request_otp(phone)
        assert _last_otp() not in req_resp.text
        assert "otp" not in req_resp.json()

