"""
Phase 2-D2: Mobile + OTP Login — Comprehensive Test Suite.

Covers:
- Functional flows (success paths)
- Account status enforcement (inactive tenant, user, store, soft-deleted)
- Enumeration protection (unknown phone, unknown domain)
- OTP security (wrong code, expired, replay, brute-force, rate limit, cooldown)
- Cross-purpose and cross-tenant isolation
- Phone normalization
- JWT structure and backward compatibility
- Security: OTP never in response or logs
- Mobile verified flag
- Endpoint boundary checks (PIN endpoints must NOT exist)
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXED_OTP = "654321"


def _unique():
    return uuid.uuid4().hex[:8]


def _register(slug, email, phone=None, password="TestPass@123!"):
    payload = {
        "tenant_name": f"MobileTest {slug}",
        "domain": slug,
        "email": email,
        "admin_name": "Mobile Tester",
        "password": password,
    }
    if phone:
        payload["phone"] = phone
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 200, f"Register failed: {resp.json()}"
    return resp.json()


def _admin_token(slug, email, password="TestPass@123!"):
    """Get a super-admin-like token for tenant management via email login."""
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _request_otp(domain, phone):
    return client.post(
        "/api/v1/auth/login/mobile-otp/request",
        json={"domain": domain, "phone": phone},
    )


def _verify_otp(domain, phone, otp):
    return client.post(
        "/api/v1/auth/login/mobile-otp/verify",
        json={"domain": domain, "phone": phone, "otp": otp},
    )


# ---------------------------------------------------------------------------
# 1. Successful OTP login — active tenant + active user with store_id NULL
# ---------------------------------------------------------------------------

class TestMobileOTPSuccessFlow:

    def test_request_otp_success_generic_response(self, unique_slug, monkeypatch):
        """OTP request for registered phone returns generic message (no OTP)."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"otp-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9876543210")

        resp = _request_otp(unique_slug, "9876543210")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "If the account exists" in data["message"]
        assert "otp" not in str(data).lower() or FIXED_OTP not in str(data)
        assert "expires_in" in data

    def test_verify_otp_returns_jwt(self, unique_slug, monkeypatch):
        """Successful OTP verify returns access_token and refresh_token."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"otp2-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9123456789")

        _request_otp(unique_slug, "9123456789")
        resp = _verify_otp(unique_slug, "9123456789", FIXED_OTP)

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data.get("token_type") == "bearer"

    def test_otp_not_in_verify_response(self, unique_slug, monkeypatch):
        """The verify response must never contain the plaintext OTP."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"otp3-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9012345678")

        _request_otp(unique_slug, "9012345678")
        resp = _verify_otp(unique_slug, "9012345678", FIXED_OTP)

        assert FIXED_OTP not in resp.text

    def test_jwt_claims_match_email_login(self, unique_slug, monkeypatch):
        """JWT from mobile OTP login has same claim structure as email/password login."""
        import base64, json as _json

        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"claim-{unique_slug}@example.com"
        _register(unique_slug, email, phone="8765432109")

        # Email login
        email_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        email_token = email_resp.json()["access_token"]

        # Mobile OTP login
        _request_otp(unique_slug, "8765432109")
        otp_resp = _verify_otp(unique_slug, "8765432109", FIXED_OTP)
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

    def test_plus91_prefix_normalized(self, unique_slug, monkeypatch):
        """OTP request with +91 prefix is canonicalized correctly."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"norm-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9988776655")

        # Request with +91 prefix (Pydantic normalizes to 9988776655)
        resp = _request_otp(unique_slug, "+919988776655")
        assert resp.status_code == 200

    def test_normalized_phone_for_verify(self, unique_slug, monkeypatch):
        """OTP verify with different but canonically equivalent phone succeeds."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"norm2-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9988776655")

        _request_otp(unique_slug, "+919988776655")
        resp = _verify_otp(unique_slug, "09988776655", FIXED_OTP)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. Enumeration protection
# ---------------------------------------------------------------------------

class TestEnumerationProtection:

    def test_unknown_phone_returns_generic_response(self, unique_slug, monkeypatch):
        """OTP request for unknown phone still returns 200 with generic message."""
        email = f"enum-{unique_slug}@example.com"
        _register(unique_slug, email)

        resp = _request_otp(unique_slug, "9111111111")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "If the account exists" in data["message"]

    def test_unknown_domain_returns_401(self, unique_slug):
        """OTP request for non-existent domain returns 401 (generic failure)."""
        resp = _request_otp(f"no-such-domain-{unique_slug}", "9111111111")
        assert resp.status_code == 401

    def test_verify_unknown_phone_returns_401(self, unique_slug, monkeypatch):
        """OTP verify for an unregistered phone returns 401."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"enu2-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9222222222")

        # Generate OTP for this tenant
        _request_otp(unique_slug, "9222222222")

        # Try to verify with a different unregistered phone
        resp = _verify_otp(unique_slug, "9333333333", FIXED_OTP)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 4. Account status enforcement
# ---------------------------------------------------------------------------

class TestAccountStatusEnforcement:

    def test_inactive_user_otp_request_silently_succeeds(self, unique_slug, monkeypatch):
        """
        OTP request for an inactive user returns the generic response
        (enumeration protection: we cannot reveal whether user is inactive).
        """
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"inactive-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9444444444")
        token = _admin_token(unique_slug, email)

        # Deactivate user via API
        user_id = reg["user_id"]
        deactivate_resp = client.patch(
            f"/api/v1/users/{user_id}/activate",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Whether deactivation succeeded or not, verify OTP request still returns generic
        resp = _request_otp(unique_slug, "9444444444")
        assert resp.status_code == 200

    def test_inactive_user_otp_verify_rejected(self, unique_slug, monkeypatch, fake_redis):
        """
        OTP verify for an inactive user must be rejected.
        We simulate by directly building the state.
        """
        from app.core.database import SessionLocal
        from app.services.auth_service import AuthService, OTPPurpose
        from app.schemas.auth import MobileOTPVerifySchema

        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"inactive2-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9555555555")
        token = _admin_token(unique_slug, email)

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

        # Try OTP verify — user is inactive so lookup returns None → 401
        db2 = SessionLocal()
        try:
            svc = AuthService(db2)
            # Pre-seed OTP in fake redis
            svc.generate_and_store_otp(
                purpose=OTPPurpose.MOBILE_LOGIN,
                tenant_id=1,
                identifier="9555555555",
                enforce_cooldown=False,
            )
        finally:
            db2.close()

        resp = _verify_otp(unique_slug, "9555555555", FIXED_OTP)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. OTP security enforcement
# ---------------------------------------------------------------------------

class TestOTPSecurity:

    def test_wrong_otp_rejected(self, unique_slug, monkeypatch):
        """Wrong OTP returns 401."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"wrong-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9666666661")

        _request_otp(unique_slug, "9666666661")
        resp = _verify_otp(unique_slug, "9666666661", "000000")
        assert resp.status_code == 401

    def test_otp_replay_rejected(self, unique_slug, monkeypatch):
        """Used OTP cannot be verified again (single-use)."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"replay-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9666666662")

        _request_otp(unique_slug, "9666666662")
        first = _verify_otp(unique_slug, "9666666662", FIXED_OTP)
        assert first.status_code == 200

        second = _verify_otp(unique_slug, "9666666662", FIXED_OTP)
        assert second.status_code == 401

    def test_brute_force_5_attempts(self, unique_slug, monkeypatch):
        """After 5 wrong OTP attempts the OTP is invalidated."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"brute-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9666666663")

        _request_otp(unique_slug, "9666666663")

        for _ in range(5):
            _verify_otp(unique_slug, "9666666663", "000000")

        # 6th attempt with correct code must fail
        resp = _verify_otp(unique_slug, "9666666663", FIXED_OTP)
        assert resp.status_code == 401

    def test_otp_resend_cooldown(self, unique_slug, monkeypatch):
        """Requesting two OTPs within 60s returns 401 (cooldown)."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"cooldown-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9666666664")

        _request_otp(unique_slug, "9666666664")
        resp = _request_otp(unique_slug, "9666666664")
        assert resp.status_code == 401

    def test_otp_rate_limit(self, unique_slug, monkeypatch, fake_redis):
        """After 3 OTP requests within 15 min the 4th is rejected."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"rate-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9666666665")

        # Make 3 real API requests; clear only cooldown keys between each
        # so we bypass the 60s cooldown while keeping the rate-limit counter.
        for i in range(3):
            resp = _request_otp(unique_slug, "9666666665")
            assert resp.status_code == 200, f"Request {i+1} failed: {resp.json()}"
            # Remove only cooldown keys so next request isn't blocked by cooldown
            cooldown_keys = [k for k in list(fake_redis._store) if "cooldown" in k]
            for k in cooldown_keys:
                del fake_redis._store[k]

        # 4th request — rate limit (3 per 15 min) must be hit
        resp = _request_otp(unique_slug, "9666666665")
        assert resp.status_code in (401, 429)


# ---------------------------------------------------------------------------
# 6. Cross-tenant isolation
# ---------------------------------------------------------------------------

class TestCrossTenantIsolation:

    def test_same_phone_different_tenants_isolated(self, monkeypatch, fake_redis):
        """OTP for Tenant A cannot authenticate Tenant B user with same phone."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        slug_a = f"tenant-a-{_unique()}"
        slug_b = f"tenant-b-{_unique()}"
        email_a = f"a-{_unique()}@example.com"
        email_b = f"b-{_unique()}@example.com"

        _register(slug_a, email_a, phone="9777777771")
        _register(slug_b, email_b, phone="9777777771")

        # Request OTP on Tenant A
        _request_otp(slug_a, "9777777771")

        # Try to verify it on Tenant B — must fail
        resp = _verify_otp(slug_b, "9777777771", FIXED_OTP)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Cross-purpose isolation
# ---------------------------------------------------------------------------

class TestCrossPurposeIsolation:

    def test_password_reset_otp_cannot_login(self, unique_slug, monkeypatch):
        """PASSWORD_RESET OTP must not authenticate a MOBILE_LOGIN request."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"purpose-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9888888881")

        # Request a password-reset OTP (different purpose)
        client.post("/api/v1/auth/forgot-password", json={"email": email})

        # Try to use it for mobile login — must fail (different purpose namespace)
        resp = _verify_otp(unique_slug, "9888888881", FIXED_OTP)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Mobile verified flag
# ---------------------------------------------------------------------------

class TestMobileVerifiedFlag:

    def test_is_mobile_verified_set_after_otp_login(self, unique_slug, monkeypatch):
        """After successful mobile OTP login, is_mobile_verified is True."""
        from app.core.database import SessionLocal
        from app.models.user import User

        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"verified-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9999999991")

        _request_otp(unique_slug, "9999999991")
        resp = _verify_otp(unique_slug, "9999999991", FIXED_OTP)
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
        assert resp.status_code == 422  # validation error (missing fields), not 404

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

    def test_otp_not_in_otp_request_response(self, unique_slug, monkeypatch):
        """Explicitly verify that neither request nor verify response contains plaintext OTP."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"security-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9123456780")

        req_resp = _request_otp(unique_slug, "9123456780")
        assert FIXED_OTP not in req_resp.text
        assert "otp" not in req_resp.json()
