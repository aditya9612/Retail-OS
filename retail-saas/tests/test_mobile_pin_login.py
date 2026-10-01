"""
Phase 2-D3: Mobile + PIN Login — Comprehensive Test Suite.

Covers:
1. Successful mobile + PIN login
2. Correct JWT response
3. JWT claims match email/password login
4. JWT claims match mobile OTP login
5. Invalid domain
6. Inactive tenant
7. Unknown phone
8. Inactive user
9. Soft-deleted user
10. Inactive store
11. Cross-tenant store mismatch
12. Tenant-level user with store_id = NULL
13. Wrong PIN
14. 5 failed PIN attempts
15. PIN lock after 5 failures
16. Login rejected while locked
17. Lock expires after 15 minutes
18. Successful login clears failed-attempt state
19. Same phone in two tenants has isolated PIN brute-force state
20. PIN lock does not affect OTP login
21. PIN lock does not affect email/password login
22. Non-numeric PIN rejected
23. PIN shorter than 4 digits rejected
24. PIN longer than 4 digits rejected
25. PIN is never returned in API response
26. pin_hash is never returned in API response
27. Existing email/password login regression
28. Existing mobile OTP login regression
29. Existing refresh/logout behavior regression
30. PIN management endpoints exist and enforce auth/payload
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

client = TestClient(app)

FIXED_OTP = "654321"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique():
    return uuid.uuid4().hex[:8]


def _register(slug, email, phone="9876543210", password="TestPass@123!"):
    payload = {
        "tenant_name": f"PinTest {slug}",
        "domain": slug,
        "email": email,
        "admin_name": "PIN Tester",
        "password": password,
    }
    if phone:
        payload["phone"] = phone
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 200, f"Register failed: {resp.json()}"
    return resp.json()


def _set_pin(user_id: int, pin: str = "1234"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        assert user is not None
        user.pin_hash = get_password_hash(pin)
        db.commit()
    finally:
        db.close()


def _pin_login(domain: str, phone: str, pin: str):
    return client.post(
        "/api/v1/auth/login/mobile-pin",
        json={"domain": domain, "phone": phone, "pin": pin},
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
        email = f"pin-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9876543210")
        _set_pin(reg["user_id"], "1234")

        resp = _pin_login(unique_slug, "9876543210", "1234")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data.get("token_type") == "bearer"

    def test_correct_jwt_response_format(self, unique_slug):
        """2. Correct JWT response."""
        email = f"jwt-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9123456789")
        _set_pin(reg["user_id"], "4321")

        resp = _pin_login(unique_slug, "9123456789", "4321")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
        assert isinstance(data["refresh_token"], str) and len(data["refresh_token"]) > 20
        assert data["token_type"] == "bearer"

    def test_jwt_claims_match_email_password_login(self, unique_slug):
        """3. JWT claims match email/password login."""
        email = f"claims-email-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9234567890", password="TestPass@123!")
        _set_pin(reg["user_id"], "5678")

        # Email login
        email_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass@123!"})
        assert email_resp.status_code == 200
        email_claims = _decode_claims(email_resp.json()["access_token"])

        # PIN login
        pin_resp = _pin_login(unique_slug, "9234567890", "5678")
        assert pin_resp.status_code == 200
        pin_claims = _decode_claims(pin_resp.json()["access_token"])

        for key in ("sub", "tenant_id", "role", "store_id", "type"):
            assert key in pin_claims
            assert pin_claims[key] == email_claims[key]

    def test_jwt_claims_match_mobile_otp_login(self, unique_slug, monkeypatch):
        """4. JWT claims match mobile OTP login."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"claims-otp-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9345678901")
        _set_pin(reg["user_id"], "9876")

        # OTP login
        client.post("/api/v1/auth/login/mobile-otp/request", json={"domain": unique_slug, "phone": "9345678901"})
        otp_resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"domain": unique_slug, "phone": "9345678901", "otp": FIXED_OTP},
        )
        assert otp_resp.status_code == 200
        otp_claims = _decode_claims(otp_resp.json()["access_token"])

        # PIN login
        pin_resp = _pin_login(unique_slug, "9345678901", "9876")
        assert pin_resp.status_code == 200
        pin_claims = _decode_claims(pin_resp.json()["access_token"])

        for key in ("sub", "tenant_id", "role", "store_id", "type"):
            assert key in pin_claims
            assert pin_claims[key] == otp_claims[key]

    def test_tenant_level_user_store_id_null(self, unique_slug):
        """12. Tenant-level user with store_id = NULL."""
        email = f"tenant-level-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9456789012")
        _set_pin(reg["user_id"], "1122")

        resp = _pin_login(unique_slug, "9456789012", "1122")
        assert resp.status_code == 200
        claims = _decode_claims(resp.json()["access_token"])
        assert claims["store_id"] is None


# ---------------------------------------------------------------------------
# 2. Account Status & Tenant / Store Validation
# ---------------------------------------------------------------------------

class TestAccountAndStoreEnforcement:

    def test_invalid_domain_rejected(self):
        """5. Invalid domain."""
        resp = _pin_login("non-existent-domain-xyz", "9876543210", "1234")
        assert resp.status_code == 401
        assert "not found" not in resp.text.lower()
        assert "does not exist" not in resp.text.lower()

    def test_inactive_tenant_rejected(self, unique_slug):
        """6. Inactive tenant."""
        email = f"inact-t-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9567890123")
        _set_pin(reg["user_id"], "1234")

        # Deactivate tenant
        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.domain == unique_slug).first()
            tenant.is_active = False
            db.commit()
        finally:
            db.close()

        resp = _pin_login(unique_slug, "9567890123", "1234")
        assert resp.status_code == 401
        assert "inactive" not in resp.text.lower()

    def test_unknown_phone_rejected(self, unique_slug):
        """7. Unknown phone."""
        email = f"unknown-p-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9678901234")

        resp = _pin_login(unique_slug, "9999999999", "1234")
        assert resp.status_code == 401
        assert "not found" not in resp.text.lower()
        assert "not registered" not in resp.text.lower()

    def test_inactive_user_rejected(self, unique_slug):
        """8. Inactive user."""
        email = f"inact-u-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9789012345")
        _set_pin(reg["user_id"], "1234")

        # Deactivate user
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        resp = _pin_login(unique_slug, "9789012345", "1234")
        assert resp.status_code == 401
        assert "inactive" not in resp.text.lower()

    def test_soft_deleted_user_rejected(self, unique_slug):
        """9. Soft-deleted user."""
        email = f"del-u-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9890123456")
        _set_pin(reg["user_id"], "1234")

        # Soft delete user
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            user.is_deleted = True
            db.commit()
        finally:
            db.close()

        resp = _pin_login(unique_slug, "9890123456", "1234")
        assert resp.status_code == 401
        assert "deleted" not in resp.text.lower()

    def test_inactive_store_rejected(self, unique_slug):
        """10. Inactive store."""
        email = f"inact-s-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9901234567")
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

        resp = _pin_login(unique_slug, "9901234567", "1234")
        assert resp.status_code == 401
        assert "inactive" not in resp.text.lower()
        assert "store" not in resp.text.lower()

    def test_cross_tenant_store_mismatch_rejected(self, unique_slug):
        """11. Cross-tenant store mismatch."""
        email = f"cross-s-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9012345678")
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

        resp = _pin_login(unique_slug, "9012345678", "1234")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. PIN Verification & Brute-Force Protection
# ---------------------------------------------------------------------------

class TestPINBruteForceProtection:

    def test_wrong_pin_rejected(self, unique_slug):
        """13. Wrong PIN."""
        email = f"wrong-pin-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9112233445")
        _set_pin(reg["user_id"], "1234")

        resp = _pin_login(unique_slug, "9112233445", "9999")
        assert resp.status_code == 401
        assert "wrong pin" not in resp.text.lower()

    def test_five_failed_pin_attempts_locks_account(self, unique_slug, fake_redis):
        """14, 15, 16. 5 failed attempts, lock set, login rejected while locked."""
        email = f"lock-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9223344556")
        _set_pin(reg["user_id"], "1234")

        # 5 failed attempts
        for i in range(5):
            resp = _pin_login(unique_slug, "9223344556", "0000")
            assert resp.status_code == 401

        # Check Redis lock exists
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            tenant_id = user.tenant_id
        finally:
            db.close()

        lock_key = f"auth:pin:lock:{tenant_id}:9223344556"
        assert fake_redis.get(lock_key) is not None, "Redis lock key must exist after 5 failures"

        # 6th attempt (even with correct PIN) is rejected while locked
        locked_resp = _pin_login(unique_slug, "9223344556", "1234")
        assert locked_resp.status_code == 401
        assert "locked" in locked_resp.text.lower() or "authentication failed" in locked_resp.text.lower()

    def test_lock_expires_after_15_minutes_allows_login(self, unique_slug, fake_redis):
        """17. Lock expires after 15 minutes allows login again."""
        email = f"lock-expire-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9334455667")
        _set_pin(reg["user_id"], "1234")

        # 5 failed attempts
        for _ in range(5):
            _pin_login(unique_slug, "9334455667", "0000")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            tenant_id = user.tenant_id
        finally:
            db.close()

        lock_key = f"auth:pin:lock:{tenant_id}:9334455667"
        assert fake_redis.get(lock_key) is not None

        # Simulate 15 minutes expiry: lock key is gone
        del fake_redis._store[lock_key]

        # Login with correct PIN now succeeds
        resp = _pin_login(unique_slug, "9334455667", "1234")
        assert resp.status_code == 200

    def test_successful_login_clears_failed_attempt_state(self, unique_slug, fake_redis):
        """18. Successful login clears failed-attempt state."""
        email = f"clear-state-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9445566778")
        _set_pin(reg["user_id"], "1234")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == reg["user_id"]).first()
            tenant_id = user.tenant_id
        finally:
            db.close()

        attempts_key = f"auth:pin:attempts:{tenant_id}:9445566778"
        lock_key = f"auth:pin:lock:{tenant_id}:9445566778"

        # 3 failed attempts
        for _ in range(3):
            _pin_login(unique_slug, "9445566778", "0000")

        assert fake_redis.get(attempts_key) == "3"

        # Successful login on 4th attempt
        success_resp = _pin_login(unique_slug, "9445566778", "1234")
        assert success_resp.status_code == 200

        # Both attempts and lock must be cleared
        assert fake_redis.get(attempts_key) is None
        assert fake_redis.get(lock_key) is None

    def test_same_phone_different_tenants_isolated_pin_lock(self, fake_redis):
        """19. Same phone in two tenants has isolated PIN brute-force state."""
        slug_a = f"tenant-a-{_unique()}"
        slug_b = f"tenant-b-{_unique()}"
        email_a = f"a-{_unique()}@example.com"
        email_b = f"b-{_unique()}@example.com"
        shared_phone = "9556677889"

        reg_a = _register(slug_a, email_a, phone=shared_phone)
        reg_b = _register(slug_b, email_b, phone=shared_phone)
        _set_pin(reg_a["user_id"], "1111")
        _set_pin(reg_b["user_id"], "2222")

        # 5 failed attempts on Tenant A locks Tenant A
        for _ in range(5):
            _pin_login(slug_a, shared_phone, "0000")

        # Tenant A must now be locked
        resp_a = _pin_login(slug_a, shared_phone, "1111")
        assert resp_a.status_code == 401

        # Tenant B must NOT be locked and succeeds with its PIN
        resp_b = _pin_login(slug_b, shared_phone, "2222")
        assert resp_b.status_code == 200

    def test_pin_lock_does_not_affect_otp_login(self, unique_slug, monkeypatch, fake_redis):
        """20. PIN lock does not affect OTP login."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"pin-lock-otp-{unique_slug}@example.com"
        phone = "9667788990"
        reg = _register(unique_slug, email, phone=phone)
        _set_pin(reg["user_id"], "1234")

        # Lock PIN login with 5 failures
        for _ in range(5):
            _pin_login(unique_slug, phone, "0000")

        # PIN login is locked
        assert _pin_login(unique_slug, phone, "1234").status_code == 401

        # OTP login still works seamlessly
        req_resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"domain": unique_slug, "phone": phone})
        assert req_resp.status_code == 200

        verify_resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"domain": unique_slug, "phone": phone, "otp": FIXED_OTP},
        )
        assert verify_resp.status_code == 200
        assert "access_token" in verify_resp.json()

    def test_pin_lock_does_not_affect_email_password_login(self, unique_slug):
        """21. PIN lock does not affect email/password login."""
        email = f"pin-lock-pwd-{unique_slug}@example.com"
        phone = "9778899001"
        password = "UserPass@123!"
        reg = _register(unique_slug, email, phone=phone, password=password)
        _set_pin(reg["user_id"], "1234")

        # Lock PIN login with 5 failures
        for _ in range(5):
            _pin_login(unique_slug, phone, "0000")

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
        resp = _pin_login(unique_slug, "9889900112", "abcd")
        assert resp.status_code == 422

    def test_pin_shorter_than_4_digits_rejected(self, unique_slug):
        """23. PIN shorter than 4 digits rejected with 422."""
        resp = _pin_login(unique_slug, "9889900112", "123")
        assert resp.status_code == 422

    def test_pin_longer_than_4_digits_rejected(self, unique_slug):
        """24. PIN longer than 4 digits rejected with 422."""
        resp = _pin_login(unique_slug, "9889900112", "12345")
        assert resp.status_code == 422

    def test_pin_never_returned_in_response(self, unique_slug):
        """25. PIN is never returned in API response."""
        email = f"privacy-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9990011223")
        _set_pin(reg["user_id"], "7788")

        # Success response
        resp = _pin_login(unique_slug, "9990011223", "7788")
        assert "7788" not in resp.text

        # Error response
        err_resp = _pin_login(unique_slug, "9990011223", "0000")
        assert "0000" not in err_resp.text
        assert "7788" not in err_resp.text

    def test_pin_hash_never_returned_in_response(self, unique_slug):
        """26. pin_hash is never returned in API response."""
        email = f"hash-priv-{unique_slug}@example.com"
        reg = _register(unique_slug, email, phone="9001122334")
        _set_pin(reg["user_id"], "9988")

        resp = _pin_login(unique_slug, "9001122334", "9988")
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

    def test_mobile_otp_login_regression(self, unique_slug, monkeypatch):
        """28. Existing mobile OTP login regression."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: int(FIXED_OTP))
        email = f"reg-otp-{unique_slug}@example.com"
        _register(unique_slug, email, phone="9123409876")

        req = client.post("/api/v1/auth/login/mobile-otp/request", json={"domain": unique_slug, "phone": "9123409876"})
        assert req.status_code == 200

        verify = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"domain": unique_slug, "phone": "9123409876", "otp": FIXED_OTP},
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

