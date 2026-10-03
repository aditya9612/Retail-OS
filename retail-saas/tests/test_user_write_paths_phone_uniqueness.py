"""
Task 6: Audit and Enforce Global Active Phone Uniqueness Across ALL User Write Paths.

Verifies:
1. ONE active/non-deleted mobile phone = ONE user across the ENTIRE platform.
2. Cross-tenant duplicate active phones are rejected.
3. Same-tenant duplicate active phones are rejected.
4. Phone normalization prevents bypassing uniqueness via +91, leading 0, spaces, hyphens.
5. Soft-deleted users' phones are reusable.
6. Self-updates (same user keeping their own phone) succeed.
7. DB-level IntegrityError is safely caught and mapped to 409 ConflictException.
8. UserService (create_user, update_user, update_my_profile).
9. AuthService (register_tenant).
10. SuperAdminService (create_tenant, update_tenant).
11. FastAPI Router endpoints (POST /api/v1/users, PUT /api/v1/users/{id}, PUT /api/v1/users/me, POST /api/v1/auth/register).
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.v1.auth.router import router as auth_router
from app.api.v1.users.router import router as users_router
from app.core.database import SessionLocal, get_db
from app.core.exceptions import ConflictException
from app.core.security import create_access_token
from app.models.role import Role
from app.models.saas_billing import SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import RegisterRequest
from app.schemas.super_admin import SuperAdminStoreOwnerCreate, SuperAdminStoreOwnerUpdate
from app.schemas.user import MyProfileUpdate, UserCreate, UserUpdate
from app.services.auth_service import AuthService
from app.services.super_admin_service import SuperAdminService
from app.services.user_service import UserService
from app.utils.phone import normalize_phone_number


# ---------------------------------------------------------------------------
# Test App & Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    test_app = FastAPI()
    test_app.include_router(auth_router, prefix="/api/v1")
    test_app.include_router(users_router, prefix="/api/v1")
    return test_app


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(app, db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _rand():
    return uuid.uuid4().hex[:8]


import random


def _gen_phone(db=None) -> str:
    while True:
        p = f"{random.choice('6789')}{random.randint(100000000, 999999999)}"
        if db is not None:
            existing = UserRepository(db).get_active_user_by_phone(p)
            if existing:
                continue
        return p


def _setup_tenant(db, prefix: str = "t") -> tuple[Tenant, User, Role]:
    """Helper to create a fully-wired tenant with owner, staff role, and user entitlements."""
    auth_svc = AuthService(db)
    slug = f"{prefix}-{_rand()}"
    owner_phone = _gen_phone(db)
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

    # Ensure plan has 'users' entitlement configured
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


# ---------------------------------------------------------------------------
# 1. UserService.create_user Tests
# ---------------------------------------------------------------------------

def test_user_service_create_user_normalizes_and_succeeds(db):
    tenant, owner, role = _setup_tenant(db, "crt-ok")
    user_svc = UserService(db)

    base_phone = _gen_phone(db)
    phone_raw = f"+91 {base_phone[:5]} {base_phone[5:]}"
    canonical = normalize_phone_number(phone_raw)

    user_in = UserCreate(
        email=f"emp-{_rand()}@example.com",
        full_name="Valid Employee",
        password="Password123!",
        role_id=role.id,
        phone=phone_raw,
    )
    created = user_svc.create_user(tenant.id, user_in)
    assert created.id is not None
    assert created.phone == canonical
    assert created.is_active is True
    assert created.is_deleted is False


def test_user_service_create_user_duplicate_phone_same_tenant_raises_conflict(db):
    tenant, owner, role = _setup_tenant(db, "crt-dup-same")
    user_svc = UserService(db)
    phone = _gen_phone(db)

    user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"emp1-{_rand()}@example.com",
            full_name="User One",
            password="Password123!",
            role_id=role.id,
            phone=phone,
        ),
    )

    with pytest.raises(ConflictException) as exc_info:
        user_svc.create_user(
            tenant.id,
            UserCreate(
                email=f"emp2-{_rand()}@example.com",
                full_name="User Two",
                password="Password123!",
                role_id=role.id,
                phone=phone,
            ),
        )
    assert "Phone number is already registered" in str(exc_info.value.detail)


def test_user_service_create_user_duplicate_phone_cross_tenant_raises_conflict(db):
    tenant_a, _, role_a = _setup_tenant(db, "crt-x-a")
    tenant_b, _, role_b = _setup_tenant(db, "crt-x-b")
    phone = _gen_phone(db)

    user_svc = UserService(db)
    user_svc.create_user(
        tenant_a.id,
        UserCreate(
            email=f"user-a-{_rand()}@example.com",
            full_name="Tenant A User",
            password="Password123!",
            role_id=role_a.id,
            phone=phone,
        ),
    )

    # Attempting to create user in Tenant B with the same phone must fail
    with pytest.raises(ConflictException) as exc_info:
        user_svc.create_user(
            tenant_b.id,
            UserCreate(
                email=f"user-b-{_rand()}@example.com",
                full_name="Tenant B User",
                password="Password123!",
                role_id=role_b.id,
                phone=phone,
            ),
        )
    assert "Phone number is already registered" in str(exc_info.value.detail)


def test_user_service_create_user_formatted_representations_rejected(db):
    tenant, _, role = _setup_tenant(db, "crt-fmt")
    user_svc = UserService(db)
    raw_canonical = _gen_phone(db)

    user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"fmt1-{_rand()}@example.com",
            full_name="Base User",
            password="Password123!",
            role_id=role.id,
            phone=raw_canonical,
        ),
    )

    # Test +91 prefix variant
    with pytest.raises(ConflictException):
        user_svc.create_user(
            tenant.id,
            UserCreate(
                email=f"fmt2-{_rand()}@example.com",
                full_name="Plus Ninety One",
                password="Password123!",
                role_id=role.id,
                phone=f"+91{raw_canonical}",
            ),
        )

    # Test 0 prefix variant
    with pytest.raises(ConflictException):
        user_svc.create_user(
            tenant.id,
            UserCreate(
                email=f"fmt3-{_rand()}@example.com",
                full_name="Leading Zero User",
                password="Password123!",
                role_id=role.id,
                phone=f"0{raw_canonical}",
            ),
        )


def test_user_service_create_user_reuses_soft_deleted_phone(db):
    tenant_a, owner_a, role_a = _setup_tenant(db, "del-reuse-a")
    tenant_b, _, role_b = _setup_tenant(db, "del-reuse-b")
    user_svc = UserService(db)
    phone = _gen_phone(db)

    u1 = user_svc.create_user(
        tenant_a.id,
        UserCreate(
            email=f"del-emp-{_rand()}@example.com",
            full_name="Soon Deleted",
            password="Password123!",
            role_id=role_a.id,
            phone=phone,
        ),
    )

    # Soft-delete u1
    user_svc.delete_user(tenant_a.id, u1.id, current_user_id=owner_a.id)
    assert u1.is_deleted is True

    # User in Tenant B can now claim the phone
    u2 = user_svc.create_user(
        tenant_b.id,
        UserCreate(
            email=f"del-emp2-{_rand()}@example.com",
            full_name="New Claimant",
            password="Password123!",
            role_id=role_b.id,
            phone=phone,
        ),
    )
    assert u2.id is not None
    assert u2.phone == phone


def test_user_service_create_user_integrity_error_mapped(db):
    tenant, _, role = _setup_tenant(db, "crt-integ")
    user_svc = UserService(db)
    phone = _gen_phone(db)

    with patch.object(
        user_svc.repo,
        "create",
        side_effect=IntegrityError("INSERT", {}, Exception("Duplicate entry 'phone' for key 'uq_users_active_phone'")),
    ):
        with pytest.raises(ConflictException) as exc_info:
            user_svc.create_user(
                tenant.id,
                UserCreate(
                    email=f"integ-{_rand()}@example.com",
                    full_name="Integ User",
                    password="Password123!",
                    role_id=role.id,
                    phone=phone,
                ),
            )
        assert "Phone number is already registered" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# 2. UserService.update_user Tests
# ---------------------------------------------------------------------------

def test_user_service_update_user_self_update_same_phone(db):
    tenant, _, role = _setup_tenant(db, "upd-self")
    user_svc = UserService(db)
    phone = _gen_phone(db)

    user = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"self-{_rand()}@example.com",
            full_name="Self Update",
            password="Password123!",
            role_id=role.id,
            phone=phone,
        ),
    )

    # Re-sending the same phone (with or without formatting) must succeed
    updated = user_svc.update_user(
        tenant.id,
        user.id,
        UserUpdate(phone=f"+91 {phone}", full_name="Self Update Edited"),
    )
    assert updated.phone == phone
    assert updated.full_name == "Self Update Edited"


def test_user_service_update_user_to_new_phone_succeeds(db):
    tenant, _, role = _setup_tenant(db, "upd-new")
    user_svc = UserService(db)
    old_phone = _gen_phone(db)
    new_phone = _gen_phone(db)

    user = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"newp-{_rand()}@example.com",
            full_name="Phone Switcher",
            password="Password123!",
            role_id=role.id,
            phone=old_phone,
        ),
    )

    updated = user_svc.update_user(
        tenant.id,
        user.id,
        UserUpdate(phone=new_phone),
    )
    assert updated.phone == new_phone


def test_user_service_update_user_to_existing_phone_same_tenant_fails(db):
    tenant, _, role = _setup_tenant(db, "upd-same-t")
    user_svc = UserService(db)
    phone_a = _gen_phone(db)
    phone_b = _gen_phone(db)

    user_a = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"ua-{_rand()}@example.com",
            full_name="User A",
            password="Password123!",
            role_id=role.id,
            phone=phone_a,
        ),
    )
    user_b = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"ub-{_rand()}@example.com",
            full_name="User B",
            password="Password123!",
            role_id=role.id,
            phone=phone_b,
        ),
    )

    with pytest.raises(ConflictException) as exc_info:
        user_svc.update_user(
            tenant.id,
            user_b.id,
            UserUpdate(phone=phone_a),
        )
    assert "Phone number is already in use" in str(exc_info.value.detail)


def test_user_service_update_user_to_existing_phone_cross_tenant_fails(db):
    tenant_1, _, role_1 = _setup_tenant(db, "upd-x-1")
    tenant_2, _, role_2 = _setup_tenant(db, "upd-x-2")
    user_svc = UserService(db)
    phone_1 = _gen_phone(db)
    phone_2 = _gen_phone(db)

    user_1 = user_svc.create_user(
        tenant_1.id,
        UserCreate(
            email=f"u1-{_rand()}@example.com",
            full_name="Tenant One User",
            password="Password123!",
            role_id=role_1.id,
            phone=phone_1,
        ),
    )
    user_2 = user_svc.create_user(
        tenant_2.id,
        UserCreate(
            email=f"u2-{_rand()}@example.com",
            full_name="Tenant Two User",
            password="Password123!",
            role_id=role_2.id,
            phone=phone_2,
        ),
    )

    with pytest.raises(ConflictException) as exc_info:
        user_svc.update_user(
            tenant_2.id,
            user_2.id,
            UserUpdate(phone=phone_1),
        )
    assert "Phone number is already in use" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# 3. UserService.update_my_profile Tests
# ---------------------------------------------------------------------------

def test_user_service_update_my_profile_self_and_cross_conflict(db):
    tenant, _, role = _setup_tenant(db, "prof-test")
    user_svc = UserService(db)
    phone_1 = _gen_phone(db)
    phone_2 = _gen_phone(db)

    u1 = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"p1-{_rand()}@example.com",
            full_name="Profile One",
            password="Password123!",
            role_id=role.id,
            phone=phone_1,
        ),
    )
    u2 = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"p2-{_rand()}@example.com",
            full_name="Profile Two",
            password="Password123!",
            role_id=role.id,
            phone=phone_2,
        ),
    )

    # Self-update keeping same phone succeeds
    updated = user_svc.update_my_profile(
        tenant.id,
        u1.id,
        MyProfileUpdate(phone=phone_1, full_name="Profile One Edited"),
    )
    assert updated.full_name == "Profile One Edited"

    # Updating u2's profile with u1's phone raises ConflictException
    with pytest.raises(ConflictException) as exc_info:
        user_svc.update_my_profile(
            tenant.id,
            u2.id,
            MyProfileUpdate(phone=phone_1),
        )
    assert "Phone number is already in use" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# 4. AuthService.register_tenant Tests
# ---------------------------------------------------------------------------

def test_auth_service_register_tenant_unique_phone_succeeds(db):
    auth_svc = AuthService(db)
    phone = _gen_phone(db)
    slug = f"reg-ok-{_rand()}"

    owner = auth_svc.register_tenant(
        RegisterRequest(
            tenant_name=f"Store {slug}",
            domain=slug,
            email=f"admin-{slug}@example.com",
            admin_name=f"Admin {slug}",
            password="Password123!",
            phone=f"+91 {phone}",
        )
    )
    assert owner.id is not None
    assert owner.phone == phone


def test_auth_service_register_tenant_duplicate_phone_raises_conflict(db):
    auth_svc = AuthService(db)
    phone = _gen_phone(db)
    slug1 = f"reg-dup1-{_rand()}"
    slug2 = f"reg-dup2-{_rand()}"

    auth_svc.register_tenant(
        RegisterRequest(
            tenant_name=f"Store {slug1}",
            domain=slug1,
            email=f"admin-{slug1}@example.com",
            admin_name=f"Admin {slug1}",
            password="Password123!",
            phone=phone,
        )
    )

    # Attempting to register another tenant with the same phone
    with pytest.raises(ConflictException) as exc_info:
        auth_svc.register_tenant(
            RegisterRequest(
                tenant_name=f"Store {slug2}",
                domain=slug2,
                email=f"admin-{slug2}@example.com",
                admin_name=f"Admin {slug2}",
                password="Password123!",
                phone=f"+91{phone}",
            )
        )
    assert "Phone number is already registered" in str(exc_info.value.detail)


def test_auth_service_register_tenant_reuses_soft_deleted_user_phone(db):
    tenant, owner, role = _setup_tenant(db, "reg-del-reuse")
    phone = _gen_phone(db)

    # Create and delete a user
    user_svc = UserService(db)
    u = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"softdel-{_rand()}@example.com",
            full_name="Soft Del",
            password="Password123!",
            role_id=role.id,
            phone=phone,
        ),
    )
    user_svc.delete_user(tenant.id, u.id, current_user_id=owner.id)

    # Now a new tenant can register with this phone
    auth_svc = AuthService(db)
    new_slug = f"reuse-t-{_rand()}"
    new_owner = auth_svc.register_tenant(
        RegisterRequest(
            tenant_name=f"Store {new_slug}",
            domain=new_slug,
            email=f"admin-{new_slug}@example.com",
            admin_name=f"Admin {new_slug}",
            password="Password123!",
            phone=phone,
        )
    )
    assert new_owner.id is not None
    assert new_owner.phone == phone


# ---------------------------------------------------------------------------
# 5. SuperAdminService Tests
# ---------------------------------------------------------------------------

def test_super_admin_create_tenant_duplicate_owner_phone_conflict(db):
    auth_svc = AuthService(db)
    existing_phone = _gen_phone(db)
    slug_exist = f"sa-exist-{_rand()}"
    auth_svc.register_tenant(
        RegisterRequest(
            tenant_name=f"Store {slug_exist}",
            domain=slug_exist,
            email=f"exist-{slug_exist}@example.com",
            admin_name="Exist Admin",
            password="Password123!",
            phone=existing_phone,
        )
    )

    sa_svc = SuperAdminService(db)
    new_slug = f"sa-new-{_rand()}"
    with pytest.raises(ConflictException) as exc_info:
        sa_svc.create_tenant(
            SuperAdminStoreOwnerCreate(
                store_name=f"SA Store {new_slug}",
                domain=new_slug,
                owner_email=f"sa-owner-{new_slug}@example.com",
                owner_name="SA Owner",
                password="Password123!",
                owner_phone=existing_phone,
                plan_code="enterprise",
            )
        )
    assert "Phone number is already registered" in str(exc_info.value.detail)


def test_super_admin_update_tenant_owner_phone_conflict_and_self(db):
    sa_svc = SuperAdminService(db)
    slug1 = f"sa-upd1-{_rand()}"
    slug2 = f"sa-upd2-{_rand()}"
    phone1 = _gen_phone(db)
    phone2 = _gen_phone(db)

    t1 = sa_svc.create_tenant(
        SuperAdminStoreOwnerCreate(
            store_name=f"SA Store {slug1}",
            domain=slug1,
            owner_email=f"sa1-{slug1}@example.com",
            owner_name="SA Owner 1",
            password="Password123!",
            owner_phone=phone1,
            plan_code="enterprise",
        )
    )
    t2 = sa_svc.create_tenant(
        SuperAdminStoreOwnerCreate(
            store_name=f"SA Store {slug2}",
            domain=slug2,
            owner_email=f"sa2-{slug2}@example.com",
            owner_name="SA Owner 2",
            password="Password123!",
            owner_phone=phone2,
            plan_code="enterprise",
        )
    )

    # 1. Update t2's owner phone to t1's owner phone -> Conflict
    with pytest.raises(ConflictException) as exc_info:
        sa_svc.update_tenant(
            t2["id"],
            SuperAdminStoreOwnerUpdate(owner_phone=phone1),
        )
    assert "Phone number is already in use" in str(exc_info.value.detail)

    # 2. Update t1's owner keeping same phone -> Succeeded
    updated_t1 = sa_svc.update_tenant(
        t1["id"],
        SuperAdminStoreOwnerUpdate(owner_phone=phone1, owner_name="SA Owner 1 Renamed"),
    )
    assert updated_t1["name"] == t1["name"]


# ---------------------------------------------------------------------------
# 6. API Router Endpoint Tests
# ---------------------------------------------------------------------------

def test_router_create_user_duplicate_phone_returns_409(client, db):
    tenant, owner, role = _setup_tenant(db, "api-crt-dup")
    phone = _gen_phone(db)

    token = create_access_token({
        "sub": str(owner.id),
        "tenant_id": tenant.id,
        "role": "admin",
        "permissions": ["users:read", "users:write"],
    })
    headers = {"Authorization": f"Bearer {token}"}

    # First user creation succeeds
    resp1 = client.post(
        "/api/v1/users",
        data={
            "email": f"api-u1-{_rand()}@example.com",
            "full_name": "API User Alpha",
            "password": "Password123!",
            "role": "staff",
            "phone": phone,
        },
        headers=headers,
    )
    assert resp1.status_code == 201, resp1.text

    # Second user creation with same phone returns 409 Conflict
    resp2 = client.post(
        "/api/v1/users",
        data={
            "email": f"api-u2-{_rand()}@example.com",
            "full_name": "API User Beta",
            "password": "Password123!",
            "role": "staff",
            "phone": phone,
        },
        headers=headers,
    )
    assert resp2.status_code == 409, resp2.text
    assert "Phone number is already registered" in resp2.text


def test_router_update_user_duplicate_phone_returns_409_and_self_returns_200(client, db):
    tenant, owner, role = _setup_tenant(db, "api-upd-dup")
    phone1 = _gen_phone(db)
    phone2 = _gen_phone(db)

    user_svc = UserService(db)
    u1 = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"api-upd-1-{_rand()}@example.com",
            full_name="API Upd Alpha",
            password="Password123!",
            role_id=role.id,
            phone=phone1,
        ),
    )
    u2 = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"api-upd-2-{_rand()}@example.com",
            full_name="API Upd Beta",
            password="Password123!",
            role_id=role.id,
            phone=phone2,
        ),
    )

    token = create_access_token({
        "sub": str(owner.id),
        "tenant_id": tenant.id,
        "role": "admin",
        "permissions": ["users:read", "users:write"],
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Update u2 to use u1's phone -> 409
    resp_conflict = client.put(
        f"/api/v1/users/{u2.id}",
        json={"phone": phone1},
        headers=headers,
    )
    assert resp_conflict.status_code == 409, resp_conflict.text
    assert "Phone number is already in use" in resp_conflict.text

    # Update u2 keeping u2's phone -> 200
    resp_self = client.put(
        f"/api/v1/users/{u2.id}",
        json={"phone": phone2, "full_name": "API Upd Beta Renamed"},
        headers=headers,
    )
    assert resp_self.status_code == 200, resp_self.text
    assert resp_self.json()["full_name"] == "API Upd Beta Renamed"


def test_router_update_my_profile_duplicate_phone_returns_409(client, db):
    tenant, owner, role = _setup_tenant(db, "api-me-dup")
    phone1 = _gen_phone(db)
    phone2 = _gen_phone(db)

    user_svc = UserService(db)
    u1 = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"me-1-{_rand()}@example.com",
            full_name="Me Alpha",
            password="Password123!",
            role_id=role.id,
            phone=phone1,
        ),
    )
    u2 = user_svc.create_user(
        tenant.id,
        UserCreate(
            email=f"me-2-{_rand()}@example.com",
            full_name="Me Beta",
            password="Password123!",
            role_id=role.id,
            phone=phone2,
        ),
    )

    token_u2 = create_access_token({
        "sub": str(u2.id),
        "tenant_id": tenant.id,
        "role": "staff",
        "permissions": ["users:read"],
    })
    headers_u2 = {"Authorization": f"Bearer {token_u2}"}

    resp = client.put(
        "/api/v1/users/me",
        json={"phone": phone1},
        headers=headers_u2,
    )
    assert resp.status_code == 409, resp.text
    assert "Phone number is already in use" in resp.text


def test_router_register_tenant_duplicate_phone_returns_409(client, db):
    phone = _gen_phone(db)
    slug1 = f"rtr-reg1-{_rand()}"
    slug2 = f"rtr-reg2-{_rand()}"

    # First registration
    resp1 = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": f"Store {slug1}",
            "domain": slug1,
            "email": f"owner-{slug1}@example.com",
            "admin_name": "First Owner",
            "password": "Password123!",
            "phone": phone,
        },
    )
    assert resp1.status_code == 200, resp1.text

    # Second registration with same phone
    resp2 = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": f"Store {slug2}",
            "domain": slug2,
            "email": f"owner-{slug2}@example.com",
            "admin_name": "Second Owner",
            "password": "Password123!",
            "phone": f"+91 {phone}",
        },
    )
    assert resp2.status_code == 409, resp2.text
    assert "Phone number is already registered" in resp2.text
