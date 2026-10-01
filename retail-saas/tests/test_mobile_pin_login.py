"""
Phase 2-D3: Mobile + PIN Login — Comprehensive Test Suite.

Updated for Task 10:
- Domain-less mobile PIN requests (phone + pin only)
- Global phone uniqueness (unique phones per tenant)
- Dynamic OTP verification via MockSMSProvider and deterministic fixture
- Preserves all security assertions: lockout, expiration, store/tenant enforcement,
  validation, privacy, JWT claims compatibility, regression tests.
"""

import base64
import json as _json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.services.sms_provider import MockSMSProvider

client = TestClient(app)

FIXED_OTP = "654321"

_pin_phone_seq = 50000000


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique():
    return uuid.uuid4().hex[:8]


def _unique_phone() -> str:
    global _pin_phone_seq
    _pin_phone_seq += 1
    return f"9{_pin_phone_seq:09d}"


def _register(slug, email, phone=None, password="TestPass@123!"):
    if phone is None:
        phone = _unique_phone()
    payload = {
        "tenant_name": f"PinTest {slug}",
        "domain": slug,
        "email": email,
        "admin_name": "PIN Tester",
        "password": password,
        "phone": phone,
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 200, f"Register failed: {resp.json()}"
    data = resp.json()
    data["phone"] = phone
    return data


def _set_pin(user_id: int, pin: str = "1234"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        assert user is not None
        user.pin_hash = get_password_hash(pin)
        db.commit()
    finally:
        db.close()


def _pin_login(phone: str, pin: str):
    return client.post(
        "/api/v1/auth/login/mobile-pin",
        json={"phone": phone, "pin": pin},
    )


def _decode_claims(token: str):
    payload_b64 = token.split(".")[1]
    padding = 4 - len(payload_b64) % 4
    return _json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))


# ---------------------------------------------------------------------------
# 1. Success Paths & JWT Structure
# ---------------------------------------------------------------------------

class TestMobilePINSuccessFlow:

    def test_successful_mobile_pin_login(self, unique_slug):
        """1. Successful mobile + PIN login."""
        phone = _unique_phone()
        email = f"pin-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        resp = _pin_login(phone, "1234")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data.get("token_type") == "bearer"

    def test_correct_jwt_response_format(self, unique_slug):
        """2. Correct JWT response."""
        phone = _unique_phone()
        email = f"jwt-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "4321")

        resp = _pin_login(phone, "4321")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
        assert isinstance(data["refresh_token"], str) and len(data["refresh_token"]) > 20
        assert data["token_type"] == "bearer"

    def test_jwt_claims_match_email_password_login(self, unique_slug):
        """3. JWT claims match email/password login."""
        phone = _unique_phone()
        email = f"claims-email-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone, password="TestPass@123!")
        _set_pin(reg["user_id"], "5678")

        # Email login
        email_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        assert email_resp.status_code == 200
        email_claims = _decode_claims(email_resp.json()["access_token"])

        # PIN login
        pin_resp = _pin_login(phone, "5678")
        assert pin_resp.status_code == 200
        pin_claims = _decode_claims(pin_resp.json()["access_token"])

        for key in ("sub", "tenant_id", "role", "store_id", "type"):
            assert key in pin_claims
            assert pin_claims[key] == email_claims[key]

    def test_jwt_claims_match_mobile_otp_login(self, unique_slug):
        """4. JWT claims match mobile OTP login."""
        phone = _unique_phone()
        email = f"claims-otp-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "9876")

        # OTP login
        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        otp_resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": _last_otp()},
        )
        assert otp_resp.status_code == 200
        otp_claims = _decode_claims(otp_resp.json()["access_token"])

        # PIN login
        pin_resp = _pin_login(phone, "9876")
        assert pin_resp.status_code == 200
        pin_claims = _decode_claims(pin_resp.json()["access_token"])

        for key in ("sub", "tenant_id", "role", "store_id", "type"):
            assert key in pin_claims
            assert pin_claims[key] == otp_claims[key]

    def test_tenant_level_user_store_id_null(self, unique_slug):
        """12. Tenant-level user with store_id = NULL."""
        phone = _unique_phone()
        email = f"tenant-level-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1122")

        resp = _pin_login(phone, "1122")
        assert resp.status_code == 200
        claims = _decode_claims(resp.json()["access_token"])
        assert claims["store_id"] is None


# ---------------------------------------------------------------------------
# 2. Account Status & Tenant / Store Validation
# ---------------------------------------------------------------------------

class TestAccountAndStoreEnforcement:

    def test_invalid_phone_format_rejected(self):
        """5. Invalid phone format rejected with 422."""
        resp = _pin_login("12345", "1234")
        assert resp.status_code == 422

    def test_inactive_tenant_rejected(self, unique_slug):
        """6. Inactive tenant."""
        phone = _unique_phone()
        email = f"inact-t-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Deactivate tenant
        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.domain == unique_slug).first()
            tenant.is_active = False
            db.commit()
        finally:
            db.close()

        resp = _pin_login(phone, "1234")
        assert resp.status_code == 401
        assert "inactive" not in resp.text.lower()

    def test_unknown_phone_rejected(self, unique_slug):
        """7. Unknown phone."""
        email = f"unknown-p-{unique_slug}@example.com"
        _register(unique_slug, email)

        resp = _pin_login("9999999999", "1234")
        assert resp.status_code == 401
        assert "not found" not in resp.text.lower()
        assert "not registered" not in resp.text.lower()

    def test_inactive_user_rejected(self, unique_slug):
        """8. Inactive user."""
        phone = _unique_phone()
        email = f"inact-u-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Deactivate user
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        resp = _pin_login(phone, "1234")
        assert resp.status_code == 401
        assert "inactive" not in resp.text.lower()

    def test_soft_deleted_user_rejected(self, unique_slug):
        """9. Soft-deleted user."""
        phone = _unique_phone()
        email = f"del-u-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Soft delete user
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            user.is_deleted = True
            db.commit()
        finally:
            db.close()

        resp = _pin_login(phone, "1234")
        assert resp.status_code == 401
        assert "deleted" not in resp.text.lower()

    def test_inactive_store_rejected(self, unique_slug):
        """10. Inactive store."""
        phone = _unique_phone()
        email = f"inact-s-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Assign user to inactive store
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            store = Store(tenant_id=user.tenant_id, name="Inactive Store", is_active=False)
            db.add(store)
            db.flush()
            user.store_id = store.id
            db.commit()
        finally:
            db.close()

        resp = _pin_login(phone, "1234")
        assert resp.status_code == 401
        assert "inactive" not in resp.text.lower()
        assert "store" not in resp.text.lower()

    def test_cross_tenant_store_mismatch_rejected(self, unique_slug):
        """11. Cross-tenant store mismatch."""
        phone = _unique_phone()
        email = f"cross-s-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Create another tenant and store, assign user to that other tenant's store
        db = SessionLocal()
        try:
            other_tenant = Tenant(name="Other Tenant", domain=f"other-{_unique()}", is_active=True)
            db.add(other_tenant)
            db.flush()
            other_store = Store(tenant_id=other_tenant.id, name="Other Tenant Store", is_active=True)
            db.add(other_store)
            db.flush()

            user = db.query(User).filter(User.id == reg["user_id"]).first()
            user.store_id = other_store.id
            db.commit()
        finally:
            db.close()

        resp = _pin_login(phone, "1234")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. PIN Verification & Brute-Force Protection
# ---------------------------------------------------------------------------

class TestPINBruteForceProtection:

    def test_wrong_pin_rejected(self, unique_slug):
        """13. Wrong PIN."""
        phone = _unique_phone()
        email = f"wrong-pin-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        resp = _pin_login(phone, "9999")
        assert resp.status_code == 401
        assert "wrong pin" not in resp.text.lower()

    def test_five_failed_pin_attempts_locks_account(self, unique_slug, fake_redis):
        """14, 15, 16. 5 failed attempts, lock set, login rejected while locked."""
        phone = _unique_phone()
        email = f"lock-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # 5 failed attempts
        for i in range(5):
            resp = _pin_login(phone, "0000")
            assert resp.status_code == 401

        # Check Redis lock exists
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            tenant_id = user.tenant_id
        finally:
            db.close()

        lock_key = f"auth:pin:lock:{tenant_id}:{phone}"
        assert fake_redis.get(lock_key) is not None, "Redis lock key must exist after 5 failures"

        # 6th attempt (even with correct PIN) is rejected while locked
        locked_resp = _pin_login(phone, "1234")
        assert locked_resp.status_code == 401
        assert "locked" in locked_resp.text.lower() or "authentication failed" in locked_resp.text.lower()

    def test_lock_expires_after_15_minutes_allows_login(self, unique_slug, fake_redis):
        """17. Lock expires after 15 minutes allows login again."""
        phone = _unique_phone()
        email = f"lock-expire-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # 5 failed attempts
        for _ in range(5):
            _pin_login(phone, "0000")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            tenant_id = user.tenant_id
        finally:
            db.close()

        lock_key = f"auth:pin:lock:{tenant_id}:{phone}"
        assert fake_redis.get(lock_key) is not None

        # Simulate 15 minutes expiry: lock key is gone
        del fake_redis._store[lock_key]

        # Login with correct PIN now succeeds
        resp = _pin_login(phone, "1234")
        assert resp.status_code == 200

    def test_successful_login_clears_failed_attempt_state(self, unique_slug, fake_redis):
        """18. Successful login clears failed-attempt state."""
        phone = _unique_phone()
        email = f"clear-state-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            tenant_id = user.tenant_id
        finally:
            db.close()

        attempts_key = f"auth:pin:attempts:{tenant_id}:{phone}"
        lock_key = f"auth:pin:lock:{tenant_id}:{phone}"

        # 3 failed attempts
        for _ in range(3):
            _pin_login(phone, "0000")

        assert fake_redis.get(attempts_key) == "3"

        # Successful login on 4th attempt
        success_resp = _pin_login(phone, "1234")
        assert success_resp.status_code == 200

        # Both attempts and lock must be cleared
        assert fake_redis.get(attempts_key) is None
        assert fake_redis.get(lock_key) is None

    def test_same_phone_different_tenants_isolated_pin_lock(self, fake_redis):
        """19. Cross-tenant duplicate phone rejection and PIN brute-force isolation."""
        slug_a = f"tenant-a-{_unique()}"
        slug_b = f"tenant-b-{_unique()}"
        email_a = f"a-{_unique()}@example.com"
        email_b = f"b-{_unique()}@example.com"
        phone_a = _unique_phone()
        phone_b = _unique_phone()

        reg_a = _register(slug_a, email_a, phone=phone_a)

        # Cross-tenant duplicate active phone is rejected (409)
        dup_resp = client.post("/api/v1/auth/register", json={
            "tenant_name": f"PinTest {slug_b}",
            "domain": slug_b,
            "email": email_b,
            "admin_name": "PIN Tester",
            "password": "TestPass@123!",
            "phone": phone_a,
        })
        assert dup_resp.status_code == 409
        assert "already registered" in dup_resp.text.lower()

        # Register Tenant B with distinct phone_b
        reg_b = _register(slug_b, email_b, phone=phone_b)
        _set_pin(reg_a["user_id"], "1111")
        _set_pin(reg_b["user_id"], "2222")

        # 5 failed attempts on Tenant A locks phone_a
        for _ in range(5):
            _pin_login(phone_a, "0000")

        # Tenant A must now be locked
        resp_a = _pin_login(phone_a, "1111")
        assert resp_a.status_code == 401

        # Tenant B must NOT be locked and succeeds with its PIN
        resp_b = _pin_login(phone_b, "2222")
        assert resp_b.status_code == 200

    def test_pin_lock_does_not_affect_otp_login(self, unique_slug, fake_redis):
        """20. PIN lock does not affect OTP login."""
        email = f"pin-lock-otp-{unique_slug}@example.com"
        phone = _unique_phone()
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Lock PIN login with 5 failures
        for _ in range(5):
            _pin_login(phone, "0000")

        # PIN login is locked
        assert _pin_login(phone, "1234").status_code == 401

        # OTP login still works seamlessly (domain-less)
        req_resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert req_resp.status_code == 200

        verify_resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": _last_otp()},
        )
        assert verify_resp.status_code == 200
        assert "access_token" in verify_resp.json()

    def test_pin_lock_does_not_affect_email_password_login(self, unique_slug):
        """21. PIN lock does not affect email/password login."""
        phone = _unique_phone()
        email = f"pin-lock-pwd-{unique_slug}@example.com"
        password = "UserPass@123!"
        reg = _register(unique_slug, email, phone=phone, password=password)
        _set_pin(reg["user_id"], "1234")

        # Lock PIN login with 5 failures
        for _ in range(5):
            _pin_login(phone, "0000")

        # Email login still succeeds
        email_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert email_resp.status_code == 200
        assert "access_token" in email_resp.json()


# ---------------------------------------------------------------------------
# 4. Input Validation & Privacy
# ---------------------------------------------------------------------------

class TestPINValidationAndPrivacy:

    def test_non_numeric_pin_rejected(self, unique_slug):
        """22. Non-numeric PIN rejected with 422."""
        resp = _pin_login("9889900112", "abcd")
        assert resp.status_code == 422

    def test_pin_shorter_than_4_digits_rejected(self, unique_slug):
        """23. PIN shorter than 4 digits rejected with 422."""
        resp = _pin_login("9889900112", "123")
        assert resp.status_code == 422

    def test_pin_longer_than_4_digits_rejected(self, unique_slug):
        """24. PIN longer than 4 digits rejected with 422."""
        resp = _pin_login("9889900112", "12345")
        assert resp.status_code == 422

    def test_pin_never_returned_in_response(self, unique_slug):
        """25. PIN is never returned in API response."""
        phone = _unique_phone()
        email = f"privacy-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "7788")

        # Success response
        resp = _pin_login(phone, "7788")
        assert "7788" not in resp.text

        # Error response
        err_resp = _pin_login(phone, "0000")
        assert "0000" not in err_resp.text
        assert "7788" not in err_resp.text

    def test_pin_hash_never_returned_in_response(self, unique_slug):
        """26. pin_hash is never returned in API response."""
        phone = _unique_phone()
        email = f"hash-priv-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "9988")

        resp = _pin_login(phone, "9988")
        assert "pin_hash" not in resp.text


# ---------------------------------------------------------------------------
# 5. Regressions (Existing Auth Unchanged)
# ---------------------------------------------------------------------------

class TestAuthRegressions:

    def test_email_password_login_regression(self, unique_slug):
        """27. Existing email/password login regression."""
        email = f"reg-email-{unique_slug}@example.com"
        _register(unique_slug, email, password="TestPassword@123!")

        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPassword@123!"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_mobile_otp_login_regression(self, unique_slug):
        """28. Existing mobile OTP login regression."""
        phone = _unique_phone()
        email = f"reg-otp-{unique_slug}@example.com"
        _register(unique_slug, email, phone=phone)

        req = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert req.status_code == 200

        verify = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": _last_otp()},
        )
        assert verify.status_code == 200
        assert "access_token" in verify.json()

    def test_refresh_and_logout_regression(self, unique_slug):
        """29. Existing refresh/logout behavior regression."""
        email = f"reg-ref-{unique_slug}@example.com"
        _register(unique_slug, email, password="TestPassword@123!")

        login = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPassword@123!"})
        assert login.status_code == 200
        tokens = login.json()

        # Refresh
        ref_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert ref_resp.status_code == 200
        assert "access_token" in ref_resp.json()

        # Logout
        logout_resp = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert logout_resp.status_code == 200


# ---------------------------------------------------------------------------
# 6. Endpoint Existence & Contract Checks
# ---------------------------------------------------------------------------

class TestPINBoundaryChecks:

    def test_pin_setup_endpoint_requires_auth(self):
        """POST /api/v1/auth/pin/setup exists and requires authentication (401)."""
        resp = client.post("/api/v1/auth/pin/setup", json={"pin": "1234"})
        assert resp.status_code == 401

    def test_pin_change_endpoint_requires_auth(self):
        """POST /api/v1/auth/pin/change exists and requires authentication (401)."""
        resp = client.post("/api/v1/auth/pin/change", json={"current_pin": "1234", "new_pin": "5678"})
        assert resp.status_code == 401

    def test_pin_reset_request_endpoint_validates_body(self):
        """POST /api/v1/auth/pin/reset/request exists and validates body (422 on empty)."""
        resp = client.post("/api/v1/auth/pin/reset/request", json={})
        assert resp.status_code == 422

    def test_pin_reset_verify_endpoint_validates_body(self):
        """POST /api/v1/auth/pin/reset/verify exists and validates body (422 on empty)."""
        resp = client.post("/api/v1/auth/pin/reset/verify", json={})
        assert resp.status_code == 422

