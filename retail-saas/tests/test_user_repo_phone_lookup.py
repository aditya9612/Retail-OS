"""
Task 2: Focused tests for UserRepository.get_active_user_by_phone().

Verifies:
A. Existing active user is found
B. Cross-tenant lookup works without tenant_id
C. Soft-deleted user returns None
D. Unknown phone returns None
E. Different phone does not return another user
F. Global behavior — no accidental tenant filtering
G. Canonical phone match
"""

import uuid

import pytest

from app.core.database import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.repositories.user_repo import UserRepository
from app.utils.phone import normalize_phone_number


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Provide a DB session that rolls back after the test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def repo(db):
    return UserRepository(db)


def _unique():
    return uuid.uuid4().hex[:8]


def _unique_phone():
    return f"9{uuid.uuid4().int % 1000000000:09d}"


def _create_tenant(db, domain: str) -> Tenant:
    tenant = Tenant(
        name=f"Test Tenant {domain}",
        domain=domain,
        is_active=True,
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
    phone: str,
    *,
    is_deleted: bool = False,
    is_active: bool = True,
    email: str | None = None,
) -> User:
    role = _get_or_create_role(db)
    user = User(
        tenant_id=tenant.id,
        role_id=role.id,
        email=email or f"user-{_unique()}@test.com",
        password_hash="not-a-real-hash",
        full_name="Test User",
        phone=phone,
        is_deleted=is_deleted,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# A. Existing active user is found
# ---------------------------------------------------------------------------

class TestActiveUserFound:

    def test_returns_user_for_existing_active_phone(self, db, repo):
        """Active user with matching phone is returned."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone)

        result = repo.get_active_user_by_phone(phone)

        assert result is not None
        assert result.id == user.id
        assert result.phone == phone
        assert result.tenant_id == tenant.id

    def test_returned_user_has_role_loaded(self, db, repo):
        """Eager-loaded role relationship is accessible without extra query."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        user = _create_user(db, tenant, phone)

        result = repo.get_active_user_by_phone(phone)

        assert result is not None
        assert result.role is not None
        assert result.role.name == "staff"


# ---------------------------------------------------------------------------
# B. Cross-tenant lookup — method does NOT require tenant_id
# ---------------------------------------------------------------------------

class TestCrossTenantLookup:

    def test_finds_user_across_different_tenant(self, db, repo):
        """User in Tenant B is found by phone alone, no tenant_id passed."""
        tenant_a = _create_tenant(db, f"a-{_unique()}")
        tenant_b = _create_tenant(db, f"b-{_unique()}")
        phone = "8765432109"
        _create_user(db, tenant_a, "7654321098")  # different phone in tenant A
        user_b = _create_user(db, tenant_b, phone)

        result = repo.get_active_user_by_phone(phone)

        assert result is not None
        assert result.id == user_b.id
        assert result.tenant_id == tenant_b.id


# ---------------------------------------------------------------------------
# C. Soft-deleted user returns None
# ---------------------------------------------------------------------------

class TestSoftDeletedUser:

    def test_soft_deleted_user_not_returned(self, db, repo):
        """User with is_deleted=True should NOT be found."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = "9988776655"
        _create_user(db, tenant, phone, is_deleted=True)

        result = repo.get_active_user_by_phone(phone)

        assert result is None


# ---------------------------------------------------------------------------
# D. Unknown phone returns None
# ---------------------------------------------------------------------------

class TestUnknownPhone:

    def test_nonexistent_phone_returns_none(self, db, repo):
        """Phone that no user owns returns None."""
        result = repo.get_active_user_by_phone("6000000000")
        assert result is None


# ---------------------------------------------------------------------------
# E. Different phone does not return another user
# ---------------------------------------------------------------------------

class TestDifferentPhone:

    def test_different_phone_does_not_match(self, db, repo):
        """Looking up phone X must not return a user with phone Y."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        _create_user(db, tenant, "9111111111")

        result = repo.get_active_user_by_phone("9222222222")

        assert result is None


# ---------------------------------------------------------------------------
# F. Global behavior — no accidental tenant_id filter
# ---------------------------------------------------------------------------

class TestGlobalBehavior:

    def test_method_signature_has_no_tenant_param(self):
        """get_active_user_by_phone must NOT accept tenant_id."""
        import inspect
        sig = inspect.signature(UserRepository.get_active_user_by_phone)
        param_names = list(sig.parameters.keys())
        assert "tenant_id" not in param_names
        assert "domain" not in param_names
        # Only 'self' and 'canonical_phone'
        assert param_names == ["self", "canonical_phone"]

    def test_user_tenant_id_is_accessible_from_result(self, db, repo):
        """Caller can derive tenant from the returned user object."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = "7777777777"
        user = _create_user(db, tenant, phone)

        result = repo.get_active_user_by_phone(phone)

        assert result is not None
        assert result.tenant_id == tenant.id
        assert result.tenant_id == user.tenant_id


# ---------------------------------------------------------------------------
# G. Canonical phone match
# ---------------------------------------------------------------------------

class TestCanonicalPhone:

    def test_lookup_uses_canonical_form(self, db, repo):
        """Stored canonical phone matches lookup with the same canonical value."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone_core = f"{uuid.uuid4().int % 1000000000:09d}"
        raw_phone = f"+91 9{phone_core[:4]}-{phone_core[4:]}"
        canonical = normalize_phone_number(raw_phone)
        _create_user(db, tenant, canonical)

        result = repo.get_active_user_by_phone(canonical)

        assert result is not None
        assert result.phone == canonical

    def test_non_canonical_form_does_not_match(self, db, repo):
        """If the DB stores canonical '9876543210', looking up '+919876543210' should NOT match."""
        tenant = _create_tenant(db, f"t-{_unique()}")
        phone = _unique_phone()
        _create_user(db, tenant, phone)

        # Intentionally pass un-normalized form — repo expects canonical
        result = repo.get_active_user_by_phone(f"+91{phone}")

        assert result is None
