"""
Task 5: Route registration and API contract verification tests.

Verifies:
1. Route registration: All 8 mobile and PIN routes exist and do not return 404:
   - POST /api/v1/auth/login/mobile-otp/request
   - POST /api/v1/auth/login/mobile-otp/verify
   - POST /api/v1/auth/login/mobile-pin
   - POST /api/v1/auth/pin/setup
   - POST /api/v1/auth/pin/change
   - POST /api/v1/auth/pin/reset/request
   - POST /api/v1/auth/pin/reset/verify
   - POST /api/v1/auth/pin/reset

2. API Contracts & Domain-less Payload Acceptance:
   A. Mobile OTP request accepts phone-only (no domain).
   B. Mobile OTP verify accepts phone + OTP (no domain).
   C. Mobile PIN login accepts phone + PIN (no domain).
   D. PIN reset request accepts phone-only (no domain).
   E. PIN reset verify accepts phone + OTP (no domain).
   F. PIN reset accepts token + new_pin.
   G. PIN setup requires authentication (401 without token).
   H. PIN change requires authentication (401 without token).
   I. Validation behavior (422 on invalid/missing fields).
   J. Email/password login and registration contracts preserved.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth.router import router as auth_router
from app.core.database import SessionLocal, get_db
from app.core.security import create_access_token, get_password_hash
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User


# ---------------------------------------------------------------------------
# Test App and Client Setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    test_app = FastAPI()
    test_app.include_router(auth_router, prefix="/api/v1")
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


def _unique():
    return uuid.uuid4().hex[:8]


_phone_counter = 20000000


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
    email: str | None = None,
) -> User:
    role = _get_or_create_role(db)
    user_phone = phone or _unique_phone()
    user = User(
        tenant_id=tenant.id,
        role_id=role.id,
        email=email or f"user-{_unique()}@example.com",
        password_hash=get_password_hash(password),
        full_name="Test User",
        phone=user_phone,
        pin_hash=get_password_hash(pin) if pin else None,
        is_active=is_active,
        is_deleted=False,
        is_mobile_verified=False,
    )
    db.add(user)
    db.flush()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": user.role.name if user.role else "staff",
            "store_id": user.store_id,
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Route Registration (No 404s)
# ---------------------------------------------------------------------------

class TestRouteRegistration:

    def test_mobile_otp_request_route_exists(self, client):
        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={})
        assert resp.status_code != 404

    def test_mobile_otp_verify_route_exists(self, client):
        resp = client.post("/api/v1/auth/login/mobile-otp/verify", json={})
        assert resp.status_code != 404

    def test_mobile_pin_login_route_exists(self, client):
        resp = client.post("/api/v1/auth/login/mobile-pin", json={})
        assert resp.status_code != 404

    def test_pin_setup_route_exists(self, client):
        resp = client.post("/api/v1/auth/pin/setup", json={})
        assert resp.status_code != 404

    def test_pin_change_route_exists(self, client):
        resp = client.post("/api/v1/auth/pin/change", json={})
        assert resp.status_code != 404

    def test_pin_reset_request_route_exists(self, client):
        resp = client.post("/api/v1/auth/pin/reset/request", json={})
        assert resp.status_code != 404

    def test_pin_reset_verify_route_exists(self, client):
        resp = client.post("/api/v1/auth/pin/reset/verify", json={})
        assert resp.status_code != 404

    def test_pin_reset_route_exists(self, client):
        resp = client.post("/api/v1/auth/pin/reset", json={})
        assert resp.status_code != 404


# ---------------------------------------------------------------------------
# 2. API Contracts & Domain-less Payload Tests
# ---------------------------------------------------------------------------

class TestMobileOTPRequestAPI:

    def test_accepts_phone_only(self, client, db, monkeypatch):
        """A. Mobile OTP request succeeds with phone-only payload."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone)

        resp = client.post(
            "/api/v1/auth/login/mobile-otp/request",
            json={"phone": phone},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "If the account exists" in data["message"]
        assert "domain" not in str(data)

    def test_rejects_missing_phone(self, client):
        resp = client.post("/api/v1/auth/login/mobile-otp/request", json={})
        assert resp.status_code == 422


class TestMobileOTPVerifyAPI:

    def test_accepts_phone_and_otp(self, client, db, monkeypatch):
        """B. Mobile OTP verify succeeds with phone + otp payload."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone)

        # Request OTP
        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})

        # Verify OTP
        resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": "123456"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_rejects_wrong_otp(self, client, db, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123456)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone)

        client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": phone})

        resp = client.post(
            "/api/v1/auth/login/mobile-otp/verify",
            json={"phone": phone, "otp": "000000"},
        )
        assert resp.status_code == 401


class TestMobilePINLoginAPI:

    def test_accepts_phone_and_pin(self, client, db):
        """C. Mobile PIN login succeeds with phone + pin payload."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234")

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_rejects_wrong_pin(self, client, db):
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234")

        resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "9999"},
        )
        assert resp.status_code == 401


class TestPINResetAPI:

    def test_pin_reset_full_flow(self, client, db, monkeypatch):
        """D, E, F. PIN reset request -> verify -> reset cycle via endpoints."""
        from app.core.config import get_settings
        monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "false")
        get_settings.cache_clear()
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 654321)
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone, pin="1234")

        # 1. Request reset OTP (phone only)
        req_resp = client.post(
            "/api/v1/auth/pin/reset/request",
            json={"phone": phone},
        )
        assert req_resp.status_code == 200
        assert req_resp.json()["success"] is True

        # 2. Verify reset OTP (phone + otp)
        ver_resp = client.post(
            "/api/v1/auth/pin/reset/verify",
            json={"phone": phone, "otp": "654321"},
        )
        assert ver_resp.status_code == 200
        reset_token = ver_resp.json()["reset_token"]
        assert reset_token is not None

        # 3. Reset PIN (token + new_pin)
        rst_resp = client.post(
            "/api/v1/auth/pin/reset",
            json={"token": reset_token, "new_pin": "5678"},
        )
        assert rst_resp.status_code == 200
        assert rst_resp.json()["success"] is True

        # 4. Verify login with new PIN succeeds
        login_resp = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "5678"},
        )
        assert login_resp.status_code == 200


class TestPINSetupAndChangeAPI:

    def test_pin_setup_requires_auth(self, client):
        """G. PIN setup returns 401 without authentication."""
        resp = client.post("/api/v1/auth/pin/setup", json={"pin": "1234"})
        assert resp.status_code == 401

    def test_pin_change_requires_auth(self, client):
        """H. PIN change returns 401 without authentication."""
        resp = client.post("/api/v1/auth/pin/change", json={"current_pin": "1234", "new_pin": "5678"})
        assert resp.status_code == 401

    def test_pin_setup_authenticated_success(self, client, db):
        tenant = _create_tenant(db, f"t-{_unique()}")
        user = _create_user(db, tenant, _unique_phone(), pin=None)
        headers = _auth_headers(user)

        resp = client.post(
            "/api/v1/auth/pin/setup",
            json={"pin": "1234"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_pin_change_authenticated_success(self, client, db):
        tenant = _create_tenant(db, f"t-{_unique()}")
        user = _create_user(db, tenant, _unique_phone(), pin="1234")
        headers = _auth_headers(user)

        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1234", "new_pin": "9876"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestUnrelatedEndpointsPreserved:

    def test_login_endpoint_works_normally(self, client, db):
        """J. Standard email + password login endpoint works normally."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        email = f"user-{_unique()}@example.com"
        _create_user(db, tenant, _unique_phone(), email=email, password="MySecretPassword123!")

        resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "MySecretPassword123!"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_register_endpoint_still_validates_domain(self, client):
        """J. RegisterRequest endpoint validates required fields including domain."""
        resp = client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422
