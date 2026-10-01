"""
Task 8: Tests for PIN Change Brute-Force Hardening.

Verifies:
A. Correct current PIN: succeeds
B. Wrong current PIN: fails
C. Repeated wrong current PIN: attempts are counted in Redis
D. 5 failures: lockout activates for 15 minutes
E. During lockout: correct current PIN cannot bypass lockout
F. After lockout expiry: operation becomes available again
G. Successful PIN change: clears lockout/failed-attempt state
H. Different users: lockout state is isolated
I. Different tenants: lockout state is isolated
J. Wrong current PIN must NOT modify the stored PIN
K. Existing mobile PIN login lockout remains unchanged and uncoupled
L. PIN setup remains unchanged
M. PIN reset remains unchanged
N. Email/password authentication remains unchanged
"""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth.router import router as auth_router
from app.core.database import SessionLocal, get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.core.exceptions import UnauthorizedException
from app.models.role import Role
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MobilePINLoginRequest,
    PINChangeRequest,
    PINResetRequestSchema,
    PINResetVerifySchema,
    PINSetupRequest,
    RegisterRequest,
    ResetPINRequest,
)
from app.services.auth_service import (
    AuthService,
    PIN_MAX_FAILED_ATTEMPTS,
    PIN_LOCK_DURATION_SECONDS,
)
from app.services.sms_provider import MockSMSProvider


# ---------------------------------------------------------------------------
# Test Infrastructure
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


def _rand():
    return uuid.uuid4().hex[:8]


_pin_harden_phone_seq = 70000000


def _unique_phone() -> str:
    global _pin_harden_phone_seq
    _pin_harden_phone_seq += 1
    return f"9{_pin_harden_phone_seq:09d}"


def _setup_tenant(db, prefix: str = "pch") -> tuple[Tenant, User, Role]:
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
    pin: str | None = "1234",
    is_active: bool = True,
    is_deleted: bool = False,
) -> User:
    user = User(
        tenant_id=tenant.id,
        role_id=role.id,
        email=f"u-{_rand()}@example.com",
        password_hash=get_password_hash("Password123!"),
        full_name="Hardened Staff",
        phone=phone or _unique_phone(),
        pin_hash=get_password_hash(pin) if pin else None,
        pin_set_at=datetime.now(timezone.utc) if pin else None,
        is_active=is_active,
        is_deleted=is_deleted,
        is_mobile_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role.name if user.role else "staff",
    })
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Task 8 Tests
# ===========================================================================

class TestPINChangeHardening:

    def test_a_correct_current_pin_succeeds(self, client, db):
        """A. Correct current PIN successfully changes PIN."""
        tenant, _, role = _setup_tenant(db, "pch-a")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1234", "new_pin": "5678"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "PIN changed successfully"

        # Verify in DB
        db.refresh(user)
        assert verify_password("5678", user.pin_hash) is True

    def test_b_wrong_current_pin_fails(self, client, db):
        """B. Wrong current PIN returns 401."""
        tenant, _, role = _setup_tenant(db, "pch-b")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "9999", "new_pin": "5678"},
            headers=headers,
        )
        assert resp.status_code == 401
        assert "Current PIN is incorrect" in resp.text

    def test_c_repeated_wrong_current_pin_attempts_counted(self, client, db, fake_redis):
        """C. Repeated wrong current PIN attempts are incremented in Redis."""
        tenant, _, role = _setup_tenant(db, "pch-c")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        attempts_key = f"auth:pin_change:attempts:{tenant.id}:{user.id}"

        for i in range(1, 4):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "9999", "new_pin": "5678"},
                headers=headers,
            )
            val = fake_redis.get(attempts_key)
            assert val == str(i), f"Expected {i} attempts in Redis, got {val}"

    def test_d_5_failures_activates_lockout(self, client, db, fake_redis):
        """D. 5 consecutive failures triggers 15-minute lockout."""
        tenant, _, role = _setup_tenant(db, "pch-d")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        lock_key = f"auth:pin_change:lock:{tenant.id}:{user.id}"
        assert fake_redis.get(lock_key) is None

        # 4 failed attempts
        for _ in range(4):
            r = client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "9999", "new_pin": "5678"},
                headers=headers,
            )
            assert r.status_code == 401
            assert "Current PIN is incorrect" in r.text
            assert fake_redis.get(lock_key) is None

        # 5th failed attempt activates lock
        r5 = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "9999", "new_pin": "5678"},
            headers=headers,
        )
        assert r5.status_code == 401
        assert fake_redis.get(lock_key) == "1"

        # 6th attempt is blocked by lockout
        r6 = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "9999", "new_pin": "5678"},
            headers=headers,
        )
        assert r6.status_code == 401
        assert "Account is temporarily locked. Please try again later." in r6.text

    def test_e_during_lockout_correct_current_pin_cannot_bypass(self, client, db, fake_redis):
        """E. During lockout, even correct current PIN cannot bypass lockout."""
        tenant, _, role = _setup_tenant(db, "pch-e")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        # Trigger lockout with 5 wrong attempts
        for _ in range(5):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "0000", "new_pin": "5678"},
                headers=headers,
            )

        # Now send the CORRECT PIN ("1234")
        r_correct = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1234", "new_pin": "5678"},
            headers=headers,
        )
        assert r_correct.status_code == 401
        assert "Account is temporarily locked. Please try again later." in r_correct.text

        # Verify PIN was NOT changed
        db.refresh(user)
        assert verify_password("1234", user.pin_hash) is True

    def test_f_after_lockout_expiry_operation_available(self, client, db, fake_redis):
        """F. After lockout key expires/cleared, operation is available again."""
        tenant, _, role = _setup_tenant(db, "pch-f")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        # Lock the user
        for _ in range(5):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "0000", "new_pin": "5678"},
                headers=headers,
            )

        # Simulate 15-min expiry by deleting the lock key
        lock_key = f"auth:pin_change:lock:{tenant.id}:{user.id}"
        attempts_key = f"auth:pin_change:attempts:{tenant.id}:{user.id}"
        fake_redis.delete(lock_key, attempts_key)

        # Now PIN change works with correct PIN
        resp = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1234", "new_pin": "5678"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "PIN changed successfully"

    def test_g_successful_pin_change_clears_lockout_state(self, client, db, fake_redis):
        """G. Successful PIN change resets failed attempt counter and lock state."""
        tenant, _, role = _setup_tenant(db, "pch-g")
        user = _create_user(db, tenant, role, pin="1234")
        headers = _auth_headers(user)

        attempts_key = f"auth:pin_change:attempts:{tenant.id}:{user.id}"
        lock_key = f"auth:pin_change:lock:{tenant.id}:{user.id}"

        # 3 failed attempts
        for _ in range(3):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "0000", "new_pin": "5678"},
                headers=headers,
            )
        assert fake_redis.get(attempts_key) == "3"

        # Successful PIN change
        r_ok = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1234", "new_pin": "5678"},
            headers=headers,
        )
        assert r_ok.status_code == 200

        # Verify Redis state is completely cleared
        assert fake_redis.get(attempts_key) is None
        assert fake_redis.get(lock_key) is None

    def test_h_different_users_lockout_isolated(self, client, db, fake_redis):
        """H. Locking User 1 does NOT lock User 2 in the same tenant."""
        tenant, _, role = _setup_tenant(db, "pch-h")
        u1 = _create_user(db, tenant, role, pin="1111")
        u2 = _create_user(db, tenant, role, pin="2222")

        h1 = _auth_headers(u1)
        h2 = _auth_headers(u2)

        # Lock User 1
        for _ in range(5):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "0000", "new_pin": "9999"},
                headers=h1,
            )

        # User 1 is locked
        r1 = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1111", "new_pin": "9999"},
            headers=h1,
        )
        assert r1.status_code == 401
        assert "temporarily locked" in r1.text

        # User 2 can change PIN without any issue
        r2 = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "2222", "new_pin": "3333"},
            headers=h2,
        )
        assert r2.status_code == 200
        assert r2.json()["message"] == "PIN changed successfully"

    def test_i_different_tenants_lockout_isolated(self, client, db, fake_redis):
        """I. Lockout in Tenant A does NOT affect users in Tenant B."""
        t_a, _, r_a = _setup_tenant(db, "pch-ia")
        t_b, _, r_b = _setup_tenant(db, "pch-ib")

        u_a = _create_user(db, t_a, r_a, pin="1111")
        u_b = _create_user(db, t_b, r_b, pin="2222")

        h_a = _auth_headers(u_a)
        h_b = _auth_headers(u_b)

        # Lock user in Tenant A
        for _ in range(5):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "0000", "new_pin": "9999"},
                headers=h_a,
            )

        # User in Tenant B changes PIN freely
        r_b = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "2222", "new_pin": "4444"},
            headers=h_b,
        )
        assert r_b.status_code == 200
        assert r_b.json()["message"] == "PIN changed successfully"

    def test_j_wrong_current_pin_does_not_modify_stored_pin(self, client, db):
        """J. Wrong current PIN attempt leaves existing pin_hash unchanged."""
        tenant, _, role = _setup_tenant(db, "pch-j")
        user = _create_user(db, tenant, role, pin="1234")
        orig_hash = user.pin_hash
        headers = _auth_headers(user)

        client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "9999", "new_pin": "5678"},
            headers=headers,
        )

        db.refresh(user)
        assert user.pin_hash == orig_hash
        assert verify_password("1234", user.pin_hash) is True

    def test_k_mobile_pin_login_lockout_remains_uncoupled(self, client, db, fake_redis):
        """K. Mobile PIN login lockout and PIN change lockout use separate namespaces."""
        tenant, _, role = _setup_tenant(db, "pch-k")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="1234")
        headers = _auth_headers(user)

        # Lock the user on PIN change
        for _ in range(5):
            client.post(
                "/api/v1/auth/pin/change",
                json={"current_pin": "0000", "new_pin": "9999"},
                headers=headers,
            )

        # PIN change is locked
        r_chg = client.post(
            "/api/v1/auth/pin/change",
            json={"current_pin": "1234", "new_pin": "9999"},
            headers=headers,
        )
        assert r_chg.status_code == 401
        assert "temporarily locked" in r_chg.text

        # Mobile PIN login is NOT locked (can still log in with correct PIN)
        r_login = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "1234"},
        )
        assert r_login.status_code == 200
        assert "access_token" in r_login.json()

    def test_l_pin_setup_remains_unchanged(self, client, db):
        """L. PIN setup continues to work and rejects overwrites."""
        tenant, _, role = _setup_tenant(db, "pch-l")
        user = _create_user(db, tenant, role, pin=None)
        headers = _auth_headers(user)

        # Setup PIN
        r_set = client.post("/api/v1/auth/pin/setup", json={"pin": "4321"}, headers=headers)
        assert r_set.status_code == 200
        assert r_set.json()["message"] == "PIN set successfully"

        # Overwrite rejected
        r_dup = client.post("/api/v1/auth/pin/setup", json={"pin": "9999"}, headers=headers)
        assert r_dup.status_code == 409

    def test_m_pin_reset_remains_unchanged(self, client, db):
        """M. PIN reset complete lifecycle remains intact."""
        tenant, _, role = _setup_tenant(db, "pch-m")
        phone = _unique_phone()
        user = _create_user(db, tenant, role, phone=phone, pin="1111")

        # Request reset OTP
        client.post("/api/v1/auth/pin/reset/request", json={"phone": phone})
        sent_otp = MockSMSProvider.get_sent_messages()[-1][1]

        # Verify OTP
        r_ver = client.post(
            "/api/v1/auth/pin/reset/verify",
            json={"phone": phone, "otp": sent_otp},
        )
        assert r_ver.status_code == 200
        token = r_ver.json()["reset_token"]

        # Reset PIN
        r_rst = client.post(
            "/api/v1/auth/pin/reset",
            json={"token": token, "new_pin": "8888"},
        )
        assert r_rst.status_code == 200

        # Login with new PIN
        r_log = client.post(
            "/api/v1/auth/login/mobile-pin",
            json={"phone": phone, "pin": "8888"},
        )
        assert r_log.status_code == 200

    def test_n_email_password_login_remains_unchanged(self, client, db):
        """N. Standard email + password authentication remains unaffected."""
        tenant, owner, _ = _setup_tenant(db, "pch-n")

        resp = client.post(
            "/api/v1/auth/login",
            json={"email": owner.email, "password": "Password123!"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

