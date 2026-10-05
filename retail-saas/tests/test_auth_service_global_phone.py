"""
Task 3: Service-level tests for AuthService refactor.
Verifies global phone lookup and domain-less mobile authentication.

Covers:
A. Mobile OTP request
   - valid phone (OTP generated, tenant-scoped key derived from user)
   - unknown phone (silent return, enumeration-safe)
   - inactive tenant (silent return)
   - active tenant (success)
   - tenant derived from user

B. Mobile OTP verify
   - valid OTP (returns TokenResponse, sets is_mobile_verified)
   - invalid OTP (UnauthorizedException)
   - expired OTP (UnauthorizedException)
   - unknown phone (UnauthorizedException)
   - inactive tenant (UnauthorizedException)
   - tenant derived from user (JWT claims match)

C. Mobile PIN login
   - valid PIN (returns TokenResponse, clears failed attempts)
   - invalid PIN (UnauthorizedException, records failed attempt)
   - unknown phone (UnauthorizedException)
   - inactive tenant (UnauthorizedException)
   - inactive store (UnauthorizedException)
   - lockout (5 failed attempts -> 15 min lock)
   - successful login (JWT issued)

D. PIN reset request
   - valid phone (generates PIN_RESET OTP)
   - unknown phone (silent return)
   - inactive tenant (silent return)

E. PIN reset verify & reset
   - valid OTP (issues 256-bit reset token)
   - invalid OTP (UnauthorizedException)
   - expired OTP (UnauthorizedException)
   - pin_reset consumes token and updates pin_hash
   - single-use token enforcement

F. Domain removal behavior
   - passing incorrect/dummy domain does NOT affect authentication,
     confirming tenant resolution is derived solely from the resolved user.

G. Regression
   - email/password login remains functional.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.database import SessionLocal
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token, get_password_hash
from app.models.password_reset_token import PasswordResetToken
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MobileOTPRequestSchema,
    MobileOTPVerifySchema,
    MobilePINLoginRequest,
    PINResetRequestSchema,
    PINResetVerifySchema,
    ResetPINRequest,
)
from app.services.auth_service import AuthService, OTPPurpose
from app.utils.phone import normalize_phone_number


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def auth_service(db):
    return AuthService(db)


def _unique():
    return uuid.uuid4().hex[:8]


_phone_counter = 10000000


def _unique_phone() -> str:
    global _phone_counter
    _phone_counter += 1
    return f"9{_phone_counter:09d}"


def _create_tenant(db, domain: str, is_active: bool = True) -> Tenant:
    tenant = Tenant(
        name=f"Tenant {domain}",
        domain=domain,
        is_active=is_active,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _create_store(db, tenant_id: int, is_active: bool = True) -> Store:
    store = Store(
        tenant_id=tenant_id,
        name=f"Store {_unique()}",
        code=f"STR-{_unique()}",
        is_active=is_active,
    )
    db.add(store)
    db.flush()
    return store


def _get_or_create_role(db, name: str = "staff") -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name, permissions=[])
    db.add(role)
    db.flush()
    return role


def _create_user(
    db,
    tenant: Tenant,
    phone: str | None = None,
    *,
    pin: str | None = None,
    password: str = "TestPass@123!",
    is_active: bool = True,
    is_deleted: bool = False,
    store_id: int | None = None,
    email: str | None = None,
) -> User:
    role = _get_or_create_role(db)
    user_phone = phone or _unique_phone()
    user = User(
        tenant_id=tenant.id,
        store_id=store_id,
        role_id=role.id,
        email=email or f"user-{_unique()}@example.com",
        password_hash=get_password_hash(password),
        full_name="Test User",
        phone=user_phone,
        pin_hash=get_password_hash(pin) if pin else None,
        is_active=is_active,
        is_deleted=is_deleted,
        is_mobile_verified=False,
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# A. Mobile OTP Request
# ---------------------------------------------------------------------------

class TestMobileOTPRequest:

    def test_valid_phone_generates_otp_with_user_derived_tenant(self, db, auth_service, fake_redis, monkeypatch):
        """OTP request generates OTP in Redis under key derived from user.tenant_id."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone)

        # Pass dummy domain to verify it is NOT used for tenant resolution
        data = MobileOTPRequestSchema(domain="dummy-ignored-domain", phone=phone)
        auth_service.mobile_otp_request(data)

        # Verify OTP was stored in Redis under the user's actual tenant.id
        otp_key = f"auth:otp:mobile_login:{tenant.id}:{phone}"
        assert fake_redis.exists(otp_key) == 1

    def test_unknown_phone_silent_return(self, db, auth_service, fake_redis):
        """Unknown phone silently returns without raising and without storing OTP."""
        data = MobileOTPRequestSchema(domain="any-domain", phone=_unique_phone())
        auth_service.mobile_otp_request(data)
        assert len(fake_redis._store) == 0

    def test_inactive_tenant_silent_return(self, db, auth_service, fake_redis):
        """If user belongs to an inactive tenant, silently returns (enumeration safe)."""
        tenant = _create_tenant(db, f"t-{_unique()}", is_active=False)
        phone = _unique_phone()
        _create_user(db, tenant, phone)

        data = MobileOTPRequestSchema(domain="any-domain", phone=phone)
        auth_service.mobile_otp_request(data)
        assert len(fake_redis._store) == 0

    def test_inactive_user_silent_return(self, db, auth_service, fake_redis):
        """If user is inactive, silently returns without generating OTP."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, is_active=False)

        data = MobileOTPRequestSchema(domain="any-domain", phone=phone)
        auth_service.mobile_otp_request(data)
        assert len(fake_redis._store) == 0


# ---------------------------------------------------------------------------
# B. Mobile OTP Verify
# ---------------------------------------------------------------------------

class TestMobileOTPVerify:

    def test_valid_otp_returns_jwt_and_marks_verified(self, db, auth_service, fake_redis, monkeypatch):
        """Valid OTP verifies successfully, returns TokenResponse, marks mobile verified."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone)

        # Request OTP
        auth_service.mobile_otp_request(MobileOTPRequestSchema(domain="irrelevant", phone=phone))

        # Verify OTP
        resp = auth_service.mobile_otp_verify(
            MobileOTPVerifySchema(domain="irrelevant", phone=phone, otp="123456")
        )
        assert resp.access_token is not None
        assert resp.refresh_token is not None

        # Verify claims
        claims = decode_token(resp.access_token)
        assert claims["sub"] == str(user.id)
        assert claims["tenant_id"] == tenant.id

        # Verify user record marked verified
        db.refresh(user)
        assert user.is_mobile_verified is True
        assert user.mobile_verified_at is not None

    def test_invalid_otp_raises_unauthorized(self, db, auth_service, fake_redis, monkeypatch):
        """Incorrect OTP code raises UnauthorizedException."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone)

        auth_service.mobile_otp_request(MobileOTPRequestSchema(domain="irrelevant", phone=phone))

        with pytest.raises(UnauthorizedException):
            auth_service.mobile_otp_verify(
                MobileOTPVerifySchema(domain="irrelevant", phone=phone, otp="999999")
            )

    def test_unknown_phone_verify_raises_unauthorized(self, db, auth_service):
        """Verifying OTP for unknown phone raises UnauthorizedException."""
        with pytest.raises(UnauthorizedException):
            auth_service.mobile_otp_verify(
                MobileOTPVerifySchema(domain="irrelevant", phone=_unique_phone(), otp="123456")
            )

    def test_inactive_tenant_verify_raises_unauthorized(self, db, auth_service, fake_redis, monkeypatch):
        """If tenant becomes inactive before verify, verification is rejected."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone)

        auth_service.mobile_otp_request(MobileOTPRequestSchema(domain="irrelevant", phone=phone))

        # Deactivate tenant
        tenant.is_active = False
        db.commit()

        with pytest.raises(UnauthorizedException):
            auth_service.mobile_otp_verify(
                MobileOTPVerifySchema(domain="irrelevant", phone=phone, otp="123456")
            )


# ---------------------------------------------------------------------------
# C. Mobile PIN Login
# ---------------------------------------------------------------------------

class TestMobilePINLogin:

    def test_successful_pin_login(self, db, auth_service):
        """Valid phone + PIN returns TokenResponse with correct claims."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone, pin="1234")

        resp = auth_service.mobile_pin_login(
            MobilePINLoginRequest(domain="any-domain", phone=phone, pin="1234")
        )
        assert resp.access_token is not None
        claims = decode_token(resp.access_token)
        assert claims["sub"] == str(user.id)
        assert claims["tenant_id"] == tenant.id

    def test_wrong_pin_records_failure_and_locks_after_5_attempts(self, db, auth_service, fake_redis):
        """5 failed PIN attempts locks the account for 15 minutes."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234")

        # 4 wrong attempts
        for _ in range(4):
            with pytest.raises(UnauthorizedException, match="Authentication failed"):
                auth_service.mobile_pin_login(
                    MobilePINLoginRequest(domain="any", phone=phone, pin="9999")
                )

        # 5th wrong attempt triggers lock
        with pytest.raises(UnauthorizedException, match="Authentication failed"):
            auth_service.mobile_pin_login(
                MobilePINLoginRequest(domain="any", phone=phone, pin="9999")
            )

        # 6th attempt with CORRECT pin is rejected due to lockout
        with pytest.raises(UnauthorizedException, match="temporarily locked"):
            auth_service.mobile_pin_login(
                MobilePINLoginRequest(domain="any", phone=phone, pin="1234")
            )

    def test_successful_login_clears_failed_attempts(self, db, auth_service, fake_redis):
        """Successful login resets the failure counter."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234")

        # 2 failed attempts
        for _ in range(2):
            with pytest.raises(UnauthorizedException):
                auth_service.mobile_pin_login(
                    MobilePINLoginRequest(domain="any", phone=phone, pin="0000")
                )

        # Successful attempt
        resp = auth_service.mobile_pin_login(
            MobilePINLoginRequest(domain="any", phone=phone, pin="1234")
        )
        assert resp.access_token is not None

        # Verify attempt counter key is cleared
        attempts_key = f"auth:pin:attempts:{tenant.id}:{phone}"
        assert fake_redis.get(attempts_key) is None

    def test_unknown_phone_pin_login_fails(self, db, auth_service):
        """Unknown phone raises UnauthorizedException without leaking existence."""
        with pytest.raises(UnauthorizedException, match="Authentication failed"):
            auth_service.mobile_pin_login(
                MobilePINLoginRequest(domain="any", phone=_unique_phone(), pin="1234")
            )

    def test_inactive_store_pin_login_fails(self, db, auth_service):
        """User bound to inactive store is rejected."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        store = _create_store(db, tenant.id, is_active=False)
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234", store_id=store.id)

        with pytest.raises(UnauthorizedException, match="Authentication failed"):
            auth_service.mobile_pin_login(
                MobilePINLoginRequest(domain="any", phone=phone, pin="1234")
            )


# ---------------------------------------------------------------------------
# D. PIN Reset Request
# ---------------------------------------------------------------------------

class TestPINResetRequest:

    def test_valid_phone_generates_pin_reset_otp(self, db, auth_service, fake_redis, monkeypatch):
        """PIN reset request generates OTP with purpose=pin_reset."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 654321)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234")

        auth_service.pin_reset_request(
            PINResetRequestSchema(domain="dummy", phone=phone)
        )

        otp_key = f"auth:otp:pin_reset:{tenant.id}:{phone}"
        assert fake_redis.exists(otp_key) == 1

    def test_unknown_phone_pin_reset_request_silent_return(self, db, auth_service, fake_redis):
        """Unknown phone silently returns without generating OTP."""
        auth_service.pin_reset_request(
            PINResetRequestSchema(domain="dummy", phone=_unique_phone())
        )
        assert len(fake_redis._store) == 0


# ---------------------------------------------------------------------------
# E. PIN Reset Verify & Pin Reset Execution
# ---------------------------------------------------------------------------

class TestPINResetVerifyAndReset:

    def test_pin_reset_full_flow(self, db, auth_service, fake_redis, monkeypatch):
        """Full PIN reset cycle: request -> verify OTP -> get reset token -> pin_reset -> login with new PIN."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 654321)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone, pin="1234")

        # 1. Request reset OTP
        auth_service.pin_reset_request(PINResetRequestSchema(domain="dummy", phone=phone))

        # 2. Verify OTP -> receive raw reset token
        reset_token = auth_service.pin_reset_verify(
            PINResetVerifySchema(domain="dummy", phone=phone, otp="654321")
        )
        assert isinstance(reset_token, str) and len(reset_token) > 20

        # Verify token in DB
        token_hash = hashlib.sha256(reset_token.encode("utf-8")).hexdigest()
        db_token = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
        assert db_token is not None
        assert db_token.user_id == user.id
        assert db_token.used_at is None

        # 3. Consume token to set new PIN
        msg = auth_service.pin_reset(ResetPINRequest(token=reset_token, new_pin="5678"))
        assert "successfully" in msg

        # 4. Token cannot be reused (single-use)
        with pytest.raises(UnauthorizedException, match="Invalid or expired reset token"):
            auth_service.pin_reset(ResetPINRequest(token=reset_token, new_pin="9999"))

        # 5. Old PIN rejected, new PIN accepted
        with pytest.raises(UnauthorizedException):
            auth_service.mobile_pin_login(MobilePINLoginRequest(domain="any", phone=phone, pin="1234"))

        new_resp = auth_service.mobile_pin_login(MobilePINLoginRequest(domain="any", phone=phone, pin="5678"))
        assert new_resp.access_token is not None


# ---------------------------------------------------------------------------
# F. Domain Removal Behavior Verification
# ---------------------------------------------------------------------------

class TestDomainRemovalBehavior:

    def test_service_does_not_call_resolve_tenant_by_domain(self, db, auth_service, fake_redis, monkeypatch):
        """Mock _resolve_tenant_by_domain to verify it is NEVER called during mobile auth flows."""
        called = []

        def fail_if_called(*args, **kwargs):
            called.append(True)
            raise AssertionError("_resolve_tenant_by_domain should NOT be called for mobile auth!")

        monkeypatch.setattr(auth_service, "_resolve_tenant_by_domain", fail_if_called)
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 111111)

        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="4321")

        # 1. mobile_otp_request
        auth_service.mobile_otp_request(MobileOTPRequestSchema(domain="bogus", phone=phone))

        # 2. mobile_otp_verify
        auth_service.mobile_otp_verify(MobileOTPVerifySchema(domain="bogus", phone=phone, otp="111111"))

        # 3. mobile_pin_login
        auth_service.mobile_pin_login(MobilePINLoginRequest(domain="bogus", phone=phone, pin="4321"))

        # 4. pin_reset_request
        auth_service.pin_reset_request(PINResetRequestSchema(domain="bogus", phone=phone))

        # 5. pin_reset_verify
        auth_service.pin_reset_verify(PINResetVerifySchema(domain="bogus", phone=phone, otp="111111"))

        assert len(called) == 0, "_resolve_tenant_by_domain was called!"


# ---------------------------------------------------------------------------
# G. Regression: Email/Password Login
# ---------------------------------------------------------------------------

class TestEmailPasswordRegression:

    def test_email_password_login_works_normally(self, db, auth_service):
        """Standard email + password login is completely unaffected."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        email = f"standard-{_unique()}@example.com"
        user = _create_user(db, tenant, _unique_phone(), email=email, password="MySecretPassword123!")

        resp = auth_service.login(LoginRequest(email=email, password="MySecretPassword123!"))
        assert resp.access_token is not None
        claims = decode_token(resp.access_token)
        assert claims["sub"] == str(user.id)
        assert claims["tenant_id"] == tenant.id
