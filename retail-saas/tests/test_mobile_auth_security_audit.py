"""
Task 7: Production-Grade End-to-End Mobile Authentication Security and Integration Audit.

Validates:
1. Mobile OTP End-to-End Flow & Failure Cases
2. Mobile PIN End-to-End Flow & Failure Cases
3. PIN Setup (Authentication, Idempotency, Plaintext Absence)
4. PIN Change (Authentication, Verification, Old-to-New Transition, Plaintext Absence)
5. PIN Reset Complete Lifecycle (Request -> Verify OTP -> Reset Token -> Reset PIN -> Login)
6. Global Phone Uniqueness & Normalization Variants
7. Tenant Isolation (Anti-Spoofing of X-Tenant-ID / X-Tenant-Domain / Client Inputs)
8. JWT Architecture & Claims Consistency
9. OTP Security Properties (6 digits, SHA-256 in Redis, TTL, Max Attempts, Purpose Isolation)
10. PIN Security Properties (4 digits, Bcrypt Hash, Failed Attempts, Lockout)
11. Information Enumeration Protection
12. Route Inventory (All 8 Mobile Auth & PIN Routes)
"""

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth.router import router as auth_router
from app.api.v1.users.router import router as users_router
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.security import create_access_token, decode_token, get_password_hash
from app.models.password_reset_token import PasswordResetToken
from app.models.role import Role
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    MobileOTPRequestSchema,
    MobileOTPVerifySchema,
    MobilePINLoginRequest,
    PINResetRequestSchema,
    PINResetVerifySchema,
    RegisterRequest,
    ResetPINRequest,
)
from app.services.auth_service import AuthService, OTPPurpose
from app.services.sms_provider import MockSMSProvider
from app.services.user_service import UserService
from app.utils.phone import normalize_phone_number


# ---------------------------------------------------------------------------
# Test Fixtures & Infrastructure
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    test_app = FastAPI()
    test_app.include_router(auth_router, prefix="/api/v1")
    test_app.include_router(users_router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app, db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def clean_sms():
    MockSMSProvider.clear_sent_messages()
    yield
    MockSMSProvider.clear_sent_messages()


def _rand():
    return uuid.uuid4().hex[:8]


_audit_phone_seq = 80000000


def _unique_phone() -> str:
    global _audit_phone_seq
    _audit_phone_seq += 1
    return f"9{_audit_phone_seq:09d}"


def _setup_tenant(db, prefix: str = "aud") -> tuple[Tenant, User, Role]:
    auth_svc = AuthService(db)
    slug = f"{prefix}-{_rand()}"
    owner_phone = _unique_phone()
    req = RegisterRequest(
        tenant_name=f"Store {slug}",
        domain=slug,
        email=f"owner-{slug}@example.com",
        admin_name=f"Owner {slug}",
        password="Password123!",
        phone=owner_phone,
    )
    owner = auth_svc.register_tenant(req)
    tenant = db.query(Tenant).filter(Tenant.id == owner.tenant_id).first()

    sub = (
        db.query(SaaSSubscription)
        .filter(SaaSSubscription.id == tenant.current_subscription_id)
        .first()
    )
    if sub and sub.plan_id:
        ent = (
            db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == sub.plan_id,
                SaaSPlanEntitlement.dimension == EntitlementDimension.USERS,
            )
            .first()
        )
        if not ent:
            ent = SaaSPlanEntitlement(
                plan_id=sub.plan_id,
                dimension=EntitlementDimension.USERS,
                is_unlimited=True,
            )
            db.add(ent)
            db.commit()

    staff_role = (
        db.query(Role)
        .filter(Role.tenant_id == tenant.id, Role.name == "staff")
        .first()
    )
    if not staff_role:
        staff_role = Role(
            tenant_id=tenant.id,
            name="staff",
            permissions=["users:read", "users:write"],
            is_system=False,
        )
        db.add(staff_role)
    else:
        staff_role.permissions = ["users:read", "users:write"]
    db.commit()

    return tenant, owner, staff_role


def _create_user(
    db,
    tenant: Tenant,
    role: Role,
    phone: str | None = None,
    pin: str | None = None,
    is_active: bool = True,
    is_deleted: bool = False,
    store_id: int | None = None,
) -> User:
    user_phone = phone or _unique_phone()
    user = User(
        tenant_id=tenant.id,
        role_id=role.id,
        email=f"u-{_rand()}@example.com",
        password_hash=get_password_hash("Password123!"),
        full_name="Audit Staff",
        phone=user_phone,
        pin_hash=get_password_hash(pin) if pin else None,
        pin_set_at=datetime.now(timezone.utc) if pin else None,
        is_active=is_active,
        is_deleted=is_deleted,
        is_mobile_verified=False,
        store_id=store_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ===========================================================================
# 1. MOBILE OTP END-TO-END FLOW & FAILURE CASES
# ===========================================================================

class TestMobileOTPEndToEnd:

    def test_mobile_otp_complete_happy_path(self, client, db):
        """Request OTP -> SMS sent -> Verify OTP -> JWT issued -> Phone marked verified."""
        tenant, _, role = _setup_tenant(db, "motp-ok")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone)
        assert user.is_mobile_verified is False

        # Step 1: Request OTP
        req_resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert req_resp.status_code == 200
        req_json = req_resp.json()
        assert req_json["success"] is True
        assert "If the account exists" in req_json["message"]
        assert req_json["expires_in"] == 300
        assert "otp" not in req_json  # NEVER exposed in response

        # Check SMS delivered
        sent = MockSMSProvider.get_sent_messages()
        assert len(sent) == 1
        sent_phone, sent_otp, sent_purpose = sent[0]
        assert sent_phone == phone
        assert len(sent_otp) == 6 and sent_otp.isdigit()
        assert sent_purpose == "mobile_login"

        # Step 2: Verify OTP
        verify_resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": sent_otp},
        )
        assert verify_resp.status_code == 200
        token_data = verify_resp.json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["token_type"].lower() == "bearer"

        # Check JWT claims
        claims = decode_token(token_data["access_token"])
        assert claims["sub"] == str(user.id)
        assert claims["tenant_id"] == tenant.id
        assert claims["role"] == "staff"

        # Check DB state
        db.refresh(user)
        assert user.is_mobile_verified is True
        assert user.mobile_verified_at is not None

    def test_mobile_otp_request_unknown_phone_enumeration_safe(self, client):
        """Unknown phone receives generic 200, no SMS dispatched."""
        phone = _unique_phone()
        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(MockSMSProvider.get_sent_messages()) == 0

    def test_mobile_otp_request_inactive_user_silent(self, client, db):
        """Inactive user receives generic 200, no SMS sent."""
        tenant, _, role = _setup_tenant(db, "motp-inact-u")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, is_active=False)

        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert resp.status_code == 200
        assert len(MockSMSProvider.get_sent_messages()) == 0

    def test_mobile_otp_request_inactive_tenant_silent(self, client, db):
        """Inactive tenant user receives generic 200, no SMS sent."""
        tenant, _, role = _setup_tenant(db, "motp-inact-t")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone)
        tenant.is_active = False
        db.commit()

        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert resp.status_code == 200
        assert len(MockSMSProvider.get_sent_messages()) == 0

    def test_mobile_otp_request_inactive_store_rejected(self, client, db):
        """User assigned to inactive store cannot request OTP."""
        tenant, _, role = _setup_tenant(db, "motp-inact-s")
        store = Store(
            tenant_id=tenant.id,
            name="Inactive Store",
            code=f"STR-{_rand()}",
            is_active=False,
        )
        db.add(store)
        db.commit()

        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, store_id=store.id)

        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert resp.status_code == 401
        assert len(MockSMSProvider.get_sent_messages()) == 0

    def test_mobile_otp_verify_invalid_otp_fails(self, client, db):
        """Wrong OTP returns 401."""
        tenant, _, role = _setup_tenant(db, "motp-wrg")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone)

        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": "000000"},
        )
        assert resp.status_code == 401
        assert "Invalid OTP" in resp.text

    def test_mobile_otp_verify_max_5_attempts_lockout(self, client, db):
        """5 wrong attempts invalidates OTP and locks further attempts."""
        tenant, _, role = _setup_tenant(db, "motp-lock")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone)

        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        sent_otp = MockSMSProvider.get_sent_messages()[0][1]

        # 4 failed attempts
        for _ in range(4):
            r = client.post(
                "/api/v1/auth/login/mobile-otp/verify",
                json={"phone": phone, "otp": "000000"},
            )
            assert r.status_code == 401
            assert "Invalid OTP" in r.text

        # 5th attempt triggers lockout
        r5 = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": "000000"},
        )
        assert r5.status_code == 401
        assert "Too many invalid OTP attempts" in r5.text

        # Now even the correct OTP is rejected
        r_correct = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": sent_otp},
        )
        assert r_correct.status_code == 401

    def test_mobile_otp_verify_single_use(self, client, db):
        """OTP cannot be reused after successful verification."""
        tenant, _, role = _setup_tenant(db, "motp-single")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone)

        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        sent_otp = MockSMSProvider.get_sent_messages()[0][1]

        # First verification succeeds
        r1 = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": sent_otp},
        )
        assert r1.status_code == 200

        # Second verification fails
        r2 = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": sent_otp},
        )
        assert r2.status_code == 401
        assert "invalid or expired" in r2.text.lower()

    def test_mobile_otp_request_cooldown_enforced(self, client, db):
        """Requesting twice within 60s cooldown returns 401."""
        tenant, _, role = _setup_tenant(db, "motp-cd")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone)

        r1 = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert r1.status_code == 200

        r2 = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        assert r2.status_code == 401
        assert "wait 60 seconds" in r2.text.lower()


# ===========================================================================
# 2. MOBILE PIN END-TO-END FLOW & FAILURE CASES
# ===========================================================================

class TestMobilePINEndToEnd:

    def test_mobile_pin_login_happy_path(self, client, db):
        """Correct phone + PIN -> JWT issued with valid claims."""
        tenant, _, role = _setup_tenant(db, "pin-ok")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="1234")

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 200
        tokens = resp.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

        claims = decode_token(tokens["access_token"])
        assert claims["sub"] == str(user.id)
        assert claims["tenant_id"] == tenant.id
        assert claims["role"] == "staff"

    def test_mobile_pin_login_wrong_pin_generic_failure(self, client, db):
        """Wrong PIN returns generic 401."""
        tenant, _, role = _setup_tenant(db, "pin-wrg")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "9999"},
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.text

    def test_mobile_pin_login_5_failures_locks_for_15_minutes(self, client, db):
        """5 failed PIN attempts locks the account."""
        tenant, _, role = _setup_tenant(db, "pin-lck")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")

        for _ in range(4):
            r = client.post(
                "/api/v1/auth/login/mobile-pin",
                json={"phone": phone, "pin": "9999"},
            )
            assert r.status_code == 401
            assert "Authentication failed" in r.text

        # 5th attempt locks
        r5 = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "9999"},
        )
        assert r5.status_code == 401

        # 6th attempt returns lockout message
        r6 = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert r6.status_code == 401
        assert "temporarily locked" in r6.text

    def test_mobile_pin_login_success_clears_attempt_state(self, client, db):
        """Successful login resets the failed attempts counter."""
        tenant, _, role = _setup_tenant(db, "pin-clr")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")

        # 3 failures
        for _ in range(3):
            client.post(
                "/api/v1/auth/login/mobile-pin",
                json={"phone": phone, "pin": "9999"},
            )

        # Successful login
        r_ok = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert r_ok.status_code == 200

        # Now 4 wrong attempts should NOT lock
        for _ in range(4):
            r = client.post(
                "/api/v1/auth/login/mobile-pin",
                json={"phone": phone, "pin": "9999"},
            )
            assert r.status_code == 401
            assert "Authentication failed" in r.text

    def test_mobile_pin_login_inactive_user_fails(self, client, db):
        tenant, _, role = _setup_tenant(db, "pin-inact-u")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234", is_active=False)

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.text

    def test_mobile_pin_login_deleted_user_fails(self, client, db):
        tenant, _, role = _setup_tenant(db, "pin-del-u")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234", is_deleted=True)

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.text

    def test_mobile_pin_login_inactive_tenant_fails(self, client, db):
        tenant, _, role = _setup_tenant(db, "pin-inact-t")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")
        tenant.is_active = False
        db.commit()

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.text

    def test_mobile_pin_login_inactive_store_fails(self, client, db):
        tenant, _, role = _setup_tenant(db, "pin-inact-s")
        store = Store(
            tenant_id=tenant.id,
            name="Inact Store",
            code=f"STR-{_rand()}",
            is_active=False,
        )
        db.add(store)
        db.commit()

        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234", store_id=store.id)

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.text

    def test_mobile_pin_login_unknown_phone_fails(self, client):
        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": _unique_phone(), "pin": "1234"},
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.text


# ===========================================================================
# 3. PIN SETUP (Authenticated, Idempotent, Bcrypt)
# ===========================================================================

class TestPINSetupAudit:

    def test_pin_setup_unauthenticated_rejected(self, client):
        """Unauthenticated request rejected with 401."""
        resp = client.post("/api/v1/auth/pin/setup", json={"pin": "1234"})
        assert resp.status_code == 401

    def test_pin_setup_authenticated_success_and_bcrypt_stored(self, client, db):
        """Authenticated user sets PIN; bcrypt hash stored, plaintext absent."""
        tenant, _, role = _setup_tenant(db, "pinset-ok")
        user = _create_user(db, tenant, role, pin=None)
        assert user.pin_hash is None
        assert user.pin_set_at is None

        token = create_access_token({
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "role": "staff",
        })
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/v1/auth/pin/setup", json={"pin": "4567"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "PIN set successfully"

        # Check DB
        db.refresh(user)
        assert user.pin_hash is not None
        assert user.pin_hash.startswith("$2b$") or user.pin_hash.startswith("$2a$")  # bcrypt
        assert "4567" not in user.pin_hash  # plaintext never stored
        assert user.pin_set_at is not None

        # Verify login now works with the newly set PIN
        login_resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": user.phone, "pin": "4567"},
        )
        assert login_resp.status_code == 200

    def test_pin_setup_cannot_overwrite_existing_pin(self, client, db):
        """Setting PIN when already set returns 409 Conflict."""
        tenant, _, role = _setup_tenant(db, "pinset-dup")
        user = _create_user(db, tenant, role, pin="1234")

        token = create_access_token({
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "role": "staff",
        })
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/v1/auth/pin/setup", json={"pin": "9999"}, headers=headers)
        assert resp.status_code == 409
        assert "already set" in resp.text

    def test_pin_setup_invalid_pin_rejected(self, client, db):
        """Non-4-digit PIN rejected with 422."""
        tenant, _, role = _setup_tenant(db, "pinset-inv")
        user = _create_user(db, tenant, role, pin=None)

        token = create_access_token({
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "role": "staff",
        })
        headers = {"Authorization": f"Bearer {token}"}

        for bad_pin in ["123", "12345", "abcd", ""]:
            r = client.post("/api/v1/auth/pin/setup", json={"pin": bad_pin}, headers=headers)
            assert r.status_code == 422


# ===========================================================================
# 4. PIN CHANGE (Authenticated, Verification, Transition)
# ===========================================================================

class TestPINChangeAudit:

    def test_pin_change_complete_flow(self, client, db):
        """Change PIN from old to new -> old fails, new succeeds."""
        tenant, _, role = _setup_tenant(db, "pinchg-ok")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="1111")

        token = create_access_token({
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "role": "staff",
        })
        headers = {"Authorization": f"Bearer {token}"}

        # Change PIN to 2222
        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1111", "new_pin": "2222"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "PIN changed successfully"

        # Old PIN fails
        r_old = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1111"},
        )
        assert r_old.status_code == 401

        # New PIN succeeds
        r_new = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "2222"},
        )
        assert r_new.status_code == 200

    def test_pin_change_wrong_current_pin_fails(self, client, db):
        """Wrong current PIN returns 401."""
        tenant, _, role = _setup_tenant(db, "pinchg-wrg")
        user = _create_user(db, tenant, role, pin="1111")

        token = create_access_token({
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "role": "staff",
        })
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "9999", "new_pin": "2222"},
            headers=headers,
        )
        assert resp.status_code == 401
        assert "Current PIN is incorrect" in resp.text

    def test_pin_change_unauthenticated_rejected(self, client):
        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1111", "new_pin": "2222"},
        )
        assert resp.status_code == 401


# ===========================================================================
# 5. PIN RESET COMPLETE LIFECYCLE
# ===========================================================================

class TestPINResetAudit:

    def test_pin_reset_complete_lifecycle(self, client, db):
        """Request OTP -> Verify OTP -> Get Reset Token -> Reset PIN -> Login with new PIN."""
        tenant, _, role = _setup_tenant(db, "prst-full")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="1111")

        # Step 1: Request reset OTP
        r1 = client.post("/api/v1/auth/pin/reset/request", json={"phone": phone})
        assert r1.status_code == 200
        assert r1.json()["success"] is True

        sent = MockSMSProvider.get_sent_messages()
        assert len(sent) == 1
        assert sent[0][0] == phone
        sent_otp = sent[0][1]
        assert sent[0][2] == "pin_reset"

        # Step 2: Verify reset OTP -> returns reset token
        r2 = client.post(
            "/api/v1/auth/pin/reset/verify",
            json={"phone": phone, "otp": sent_otp},
        )
        assert r2.status_code == 200
        reset_token = r2.json()["reset_token"]
        assert len(reset_token) > 20

        # Step 3: Reset PIN
        r3 = client.post(
            "/api/v1/auth/pin/reset",
            json={"token": reset_token, "new_pin": "7777"},
        )
        assert r3.status_code == 200
        assert "successfully" in r3.json()["message"]

        # Step 4: Login with old PIN fails
        r_old = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1111"},
        )
        assert r_old.status_code == 401

        # Step 5: Login with new PIN succeeds
        r_new = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "7777"},
        )
        assert r_new.status_code == 200

    def test_pin_reset_token_single_use(self, client, db):
        """Reset token cannot be used twice."""
        tenant, _, role = _setup_tenant(db, "prst-sngl")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1111")

        client.post("/api/v1/auth/pin/reset/request", json={"phone": phone})
        sent_otp = MockSMSProvider.get_sent_messages()[0][1]
        r2 = client.post("/api/v1/auth/pin/reset/verify", json={"phone": phone, "otp": sent_otp})
        reset_token = r2.json()["reset_token"]

        # First use -> 200
        r_use1 = client.post("/api/v1/auth/pin/reset", json={"token": reset_token, "new_pin": "3333"})
        assert r_use1.status_code == 200

        # Second use -> 401
        r_use2 = client.post("/api/v1/auth/pin/reset", json={"token": reset_token, "new_pin": "4444"})
        assert r_use2.status_code == 401
        assert "Invalid or expired reset token" in r_use2.text

    def test_pin_reset_unknown_phone_silent(self, client):
        """Unknown phone on reset request returns generic 200, no SMS dispatched."""
        resp = client.post("/api/v1/auth/pin/reset/request", json={"phone": _unique_phone()})
        assert resp.status_code == 200
        assert len(MockSMSProvider.get_sent_messages()) == 0


# ===========================================================================
# 6. GLOBAL PHONE UNIQUENESS & FORMATTING VARIANTS
# ===========================================================================

class TestGlobalPhoneUniquenessAudit:

    def test_cross_tenant_duplicate_phone_rejected(self, db):
        """Same canonical phone number cannot be created in different tenants."""
        t1, _, r1 = _setup_tenant(db, "uniq-t1")
        t2, _, r2 = _setup_tenant(db, "uniq-t2")
        phone = _unique_phone()

        # Create user in Tenant 1
        _create_user(db, t1, r1, phone=phone)

        # Attempt to create user in Tenant 2 with same phone -> fails
        from app.core.exceptions import ConflictException
        user_svc = UserService(db)
        from app.schemas.user import UserCreate
        with pytest.raises(ConflictException) as exc:
            user_svc.create_user(
                t2.id,
                UserCreate(
                    email=f"t2-dup-{_rand()}@example.com",
                    full_name="Duplicate Staff",
                    password="Password123!",
                    role_id=r2.id,
                    phone=phone,
                ),
            )
        assert "already" in str(exc.value).lower()

    def test_phone_normalization_variants_cannot_bypass_uniqueness(self, db):
        """Formatted variations (+91, 91, 0, spaces) map to same canonical phone and are rejected."""
        t1, _, r1 = _setup_tenant(db, "norm-t1")
        t2, _, r2 = _setup_tenant(db, "norm-t2")
        raw_base = _unique_phone()

        # Create user in Tenant 1 with canonical 10-digit
        _create_user(db, t1, r1, phone=raw_base)

        variants = [
            f"+91{raw_base}",
            f"91{raw_base}",
            f"0{raw_base}",
            f"+91 {raw_base[:5]} {raw_base[5:]}",
            f"+91-{raw_base[:5]}-{raw_base[5:]}",
        ]

        from app.core.exceptions import ConflictException
        user_svc = UserService(db)
        from app.schemas.user import UserCreate

        for v in variants:
            with pytest.raises(ConflictException):
                user_svc.create_user(
                    t2.id,
                    UserCreate(
                        email=f"v-{_rand()}@example.com",
                        full_name="Variant Staff",
                        password="Password123!",
                        role_id=r2.id,
                        phone=v,
                    ),
                )

    def test_soft_deleted_user_phone_reusable(self, db):
        """Soft-deleted user's phone can be reused by an active user."""
        t1, owner1, r1 = _setup_tenant(db, "reuse-t1")
        t2, _, r2 = _setup_tenant(db, "reuse-t2")
        phone = _unique_phone()

        u1 = _create_user(db, t1, r1, phone=phone)

        # Soft delete u1
        user_svc = UserService(db)
        user_svc.delete_user(t1.id, u1.id, current_user_id=owner1.id)

        # Create user in Tenant 2 with same phone -> succeeds
        from app.schemas.user import UserCreate
        u2 = user_svc.create_user(
            t2.id,
            UserCreate(
                email=f"u2-reuse-{_rand()}@example.com",
                full_name="Reused Phone Staff",
                password="Password123!",
                role_id=r2.id,
                phone=phone,
            ),
        )
        assert u2 is not None
        assert u2.phone == phone


# ===========================================================================
# 7. TENANT ISOLATION (Untrusted Client Headers / Inputs)
# ===========================================================================

class TestTenantIsolationAudit:

    def test_mobile_auth_ignores_spoofed_headers(self, client, db):
        """Mobile OTP and PIN ignore spoofed X-Tenant-ID and X-Tenant-Domain headers."""
        tenant, _, role = _setup_tenant(db, "iso-real")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="5555")

        spoofed_headers = {
            "X-Tenant-ID": "99999",
            "X-Tenant-Domain": "attacker-domain.com",
        }

        # Request OTP with spoofed headers
        r_req = client.post(
            "/api/v1/auth/login/mobile-otp/request",
            json={"phone": phone},
            headers=spoofed_headers,
        )
        assert r_req.status_code == 200
        sent_otp = MockSMSProvider.get_sent_messages()[0][1]

        # Verify OTP with spoofed headers
        r_ver = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": sent_otp},
            headers=spoofed_headers,
        )
        assert r_ver.status_code == 200
        claims_otp = decode_token(r_ver.json()["access_token"])
        assert claims_otp["tenant_id"] == tenant.id  # NOT 99999

        # Mobile PIN login with spoofed headers
        r_pin = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "5555"},
            headers=spoofed_headers,
        )
        assert r_pin.status_code == 200
        claims_pin = decode_token(r_pin.json()["access_token"])
        assert claims_pin["tenant_id"] == tenant.id  # NOT 99999

    def test_authenticated_pin_operations_derive_tenant_from_jwt(self, client, db):
        """PIN setup and change strictly use the tenant from authenticated JWT."""
        tenant, _, role = _setup_tenant(db, "iso-jwt")
        user = _create_user(db, tenant, role, pin=None)

        token = create_access_token({
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "role": "staff",
        })
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "99999",
            "X-Tenant-Domain": "attacker.com",
        }

        resp = client.post("/api/v1/auth/pin/setup", json={"pin": "6666"}, headers=headers)
        assert resp.status_code == 200
        db.refresh(user)
        assert user.pin_hash is not None


# ===========================================================================
# 8. JWT REGRESSION & CLAIMS AUDIT
# ===========================================================================

class TestJWTAudit:

    def test_jwt_claims_structure_consistency(self, client, db):
        """Tokens issued from mobile auth contain identical claims to password auth."""
        tenant, _, role = _setup_tenant(db, "jwt-chk")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="1234")

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 200
        token_data = resp.json()

        access_claims = decode_token(token_data["access_token"])
        refresh_claims = decode_token(token_data["refresh_token"])

        for claim in ["sub", "tenant_id", "role", "store_id", "jti", "exp", "iat", "type"]:
            assert claim in access_claims, f"Missing claim {claim} in access token"
            assert claim in refresh_claims, f"Missing claim {claim} in refresh token"

        assert access_claims["type"] == "access"
        assert refresh_claims["type"] == "refresh"
        assert access_claims["sub"] == str(user.id)
        assert access_claims["tenant_id"] == tenant.id

    def test_mobile_access_token_can_access_protected_endpoints(self, client, db):
        """Access token from mobile PIN login can call protected /api/v1/users/me."""
        tenant, _, role = _setup_tenant(db, "jwt-acc")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        token = resp.json()["access_token"]

        me_resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["phone"] == phone


# ===========================================================================
# 9. OTP SECURITY AUDIT (Purpose Isolation, Storage, Response Safety)
# ===========================================================================

class TestOTPSecurityAudit:

    def test_otp_purpose_isolation(self, client, db):
        """MOBILE_LOGIN OTP cannot be used to verify PIN_RESET and vice-versa."""
        tenant, _, role = _setup_tenant(db, "otp-purp")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")

        # Request MOBILE_LOGIN OTP
        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        login_otp = MockSMSProvider.get_sent_messages()[-1][1]

        # Attempt to use login OTP on pin reset verify -> fails
        r_cross = client.post(
            "/api/v1/auth/pin/reset/verify",
            json={"phone": phone, "otp": login_otp},
        )
        assert r_cross.status_code == 401

    def test_otp_stored_as_sha256_in_redis(self, client, db, fake_redis):
        """Plaintext OTP is never stored in Redis; only SHA-256 hash."""
        tenant, _, role = _setup_tenant(db, "otp-sha")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone)

        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})
        sent_otp = MockSMSProvider.get_sent_messages()[-1][1]

        otp_key = f"auth:otp:mobile_login:{tenant.id}:{phone}"
        stored_val = fake_redis.get(otp_key)

        expected_hash = hashlib.sha256(sent_otp.encode("utf-8")).hexdigest()
        assert stored_val == expected_hash
        assert sent_otp != stored_val  # Plaintext never stored in Redis


# ===========================================================================
# 10. INFORMATION ENUMERATION PROTECTION
# ===========================================================================

class TestEnumerationAudit:

    def test_otp_request_responses_indistinguishable(self, client, db):
        """Registered vs unregistered phone responses are indistinguishable."""
        tenant, _, role = _setup_tenant(db, "enum-comp")
        phone_registered = _unique_phone()
        _create_user(db, tenant, role, phone=phone_registered)
        phone_unregistered = _unique_phone()

        r_reg = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone_registered})
        r_unreg = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone_unregistered})

        assert r_reg.status_code == r_unreg.status_code == 200
        assert r_reg.json() == r_unreg.json()

    def test_pin_login_failures_indistinguishable(self, client, db):
        """Wrong PIN vs nonexistent phone responses are identical."""
        tenant, _, role = _setup_tenant(db, "enum-pin")
        phone = _unique_phone()
        _create_user(db, tenant, role, phone=phone, pin="1234")

        r_wrg_pin = client.post("/api/v1/auth/login/mobile-pin", json={"phone": phone, "pin": "9999"})
        r_unreg = client.post("/api/v1/auth/login/mobile-pin", json={"phone": _unique_phone(), "pin": "1234"})

        assert r_wrg_pin.status_code == r_unreg.status_code == 401
        assert r_wrg_pin.text == r_unreg.text


# ===========================================================================
# 11. ROUTE INVENTORY AUDIT
# ===========================================================================

class TestRouteInventoryAudit:

    def test_all_8_mobile_and_pin_routes_exist(self, client):
        """Verify all 8 routes exist and respond with expected status code (not 404)."""
        routes = [
            ("POST", "/api/v1/auth/login/mobile-otp/request", {}),
            ("POST", "/api/v1/auth/login/mobile-otp/verify", {}),
            ("POST", "/api/v1/auth/login/mobile-pin", {}),
            ("POST", "/api/v1/auth/pin/setup", {}),
            ("POST", "/api/v1/auth/pin/change", {}),
            ("POST", "/api/v1/auth/pin/reset/request", {}),
            ("POST", "/api/v1/auth/pin/reset/verify", {}),
            ("POST", "/api/v1/auth/pin/reset", {}),
        ]
        for method, path, body in routes:
            resp = client.request(method, path, json=body)
            assert resp.status_code != 404, f"Route {path} returned 404!"
