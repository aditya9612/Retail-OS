import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.super_admin import SuperAdminCreate
from app.services.super_admin_service import SuperAdminService

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def super_admin_fixture(db_session):
    uid = uuid.uuid4().hex[:6]
    name_suffix = "".join([c for c in uid if c.isalpha()] or ["Alpha"])
    email = f"sa_{uid}@example.com"
    password = "SuperPassword@123!"
    data = SuperAdminCreate(
        email=email,
        full_name=f"Super Admin {name_suffix}",
        password=password,
        phone="9876543210",
    )
    # Use service (bootstrap path)
    sa = SuperAdminService(db_session).create_super_admin(data)
    return {"super_admin": sa, "email": email, "password": password}


@pytest.fixture
def tenant_fixture(db_session):
    uid = uuid.uuid4().hex[:6]
    email = f"tenant_admin_{uid}@example.com"
    password = "TenantPassword@123!"
    reg_payload = {
        "tenant_name": f"Test Tenant {uid}",
        "domain": f"tt-{uid}",
        "email": email,
        "admin_name": f"Tenant Admin {uid}",
        "password": password,
        "phone": f"91{uuid.uuid4().int % 100000000:08d}",
    }
    r = client.post("/api/v1/auth/register", json=reg_payload)
    assert r.status_code == 200, f"Registration failed: {r.text}"
    tenant_id = r.json()["tenant_id"]

    login_r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]

    return {
        "tenant_id": tenant_id,
        "token": token,
        "email": email,
        "password": password,
        "domain": reg_payload["domain"],
        "name": reg_payload["tenant_name"],
    }


def test_sec01_anonymous_user_cannot_create_super_admin():
    """SEC-01: Verify anonymous requests to POST /api/v1/super-admins are rejected with 401."""
    payload = {
        "email": f"hacker_{uuid.uuid4().hex[:6]}@example.com",
        "full_name": "Anonymous Attacker",
        "password": "HackerPassword@123!",
        "phone": "9876543210",
    }
    r = client.post("/api/v1/super-admins", json=payload)
    assert r.status_code == 401, f"Expected 401 Unauthorized, got {r.status_code}: {r.text}"


def test_sec01_tenant_user_cannot_create_super_admin(tenant_fixture):
    """SEC-01: Verify tenant user token cannot call POST /api/v1/super-admins."""
    payload = {
        "email": f"tenant_escalated_{uuid.uuid4().hex[:6]}@example.com",
        "full_name": "Escalated User",
        "password": "HackerPassword@123!",
        "phone": "9876543210",
    }
    headers = {"Authorization": f"Bearer {tenant_fixture['token']}"}
    r = client.post("/api/v1/super-admins", json=payload, headers=headers)
    assert r.status_code == 401, f"Expected 401 Unauthorized, got {r.status_code}: {r.text}"


def test_sec01_authenticated_super_admin_can_create_another_super_admin(super_admin_fixture):
    """SEC-01: Authenticated Super Admin can create additional Super Admins."""
    # 1. Login as Super Admin
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]

    # 2. Create another Super Admin
    new_email = f"second_sa_{uuid.uuid4().hex[:6]}@example.com"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "email": new_email,
        "full_name": "Second Super Admin",
        "password": "SecondPassword@123!",
        "phone": "9876543211",
    }
    create_r = client.post("/api/v1/super-admins", json=payload, headers=headers)
    assert create_r.status_code == 201
    assert create_r.json()["email"] == new_email


def test_super_admin_login_and_token_refresh(super_admin_fixture):
    """Verify Super Admin login and refresh token flow."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    assert login_r.status_code == 200
    tokens = login_r.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # Test refresh
    refresh_r = client.post(
        "/api/v1/super-admins/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_r.status_code == 200
    new_tokens = refresh_r.json()
    assert "access_token" in new_tokens


def test_tenant_token_rejected_on_super_admin_routes(tenant_fixture):
    """Verify tenant token is rejected on Super Admin endpoints."""
    headers = {"Authorization": f"Bearer {tenant_fixture['token']}"}
    r = client.get("/api/v1/super-admins/dashboard", headers=headers)
    assert r.status_code == 401


def test_super_admin_self_delete_protection(super_admin_fixture):
    """Verify Super Admin cannot delete their own account."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    token = login_r.json()["access_token"]
    sa_id = super_admin_fixture["super_admin"].id

    headers = {"Authorization": f"Bearer {token}"}
    del_r = client.delete(f"/api/v1/super-admins/{sa_id}", headers=headers)
    assert del_r.status_code == 409
    res_text = del_r.text.lower()
    assert "cannot delete your own" in res_text


def test_sec02_tenant_suspension_immediately_blocks_active_jwt(super_admin_fixture, tenant_fixture):
    """SEC-02: Verifies that deactivating a tenant immediately blocks access on already-issued JWTs."""
    tenant_id = tenant_fixture["tenant_id"]
    tenant_token = tenant_fixture["token"]
    headers = {"Authorization": f"Bearer {tenant_token}"}

    # 1. Verify active token works before suspension
    me_r = client.get("/api/v1/users/me", headers=headers)
    assert me_r.status_code == 200

    # 2. Login as Super Admin and suspend the tenant
    sa_login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    sa_token = sa_login_r.json()["access_token"]
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    suspend_r = client.patch(
        f"/api/v1/super-admins/tenants/{tenant_id}/status",
        json={"is_active": False},
        headers=sa_headers,
    )
    assert suspend_r.status_code == 200
    assert suspend_r.json()["is_active"] is False

    # 3. Reuse the PREVIOUSLY ISSUED tenant JWT — MUST BE REJECTED IMMEDIATELY!
    recheck_r = client.get("/api/v1/users/me", headers=headers)
    assert recheck_r.status_code == 401, f"Expected 401 Unauthorized for suspended tenant, got {recheck_r.status_code}: {recheck_r.text}"
    recheck_text = recheck_r.text.lower()
    assert "tenant" in recheck_text or "disabled" in recheck_text

    # 4. Reactivate tenant and confirm access is restored
    reactivate_r = client.patch(
        f"/api/v1/super-admins/tenants/{tenant_id}/status",
        json={"is_active": True},
        headers=sa_headers,
    )
    assert reactivate_r.status_code == 200
    assert reactivate_r.json()["is_active"] is True

    # 5. Access should now be restored with the same valid JWT
    restored_r = client.get("/api/v1/users/me", headers=headers)
    assert restored_r.status_code == 200


def test_p1_list_tenants_default_pagination(super_admin_fixture, tenant_fixture):
    """P1: Verify default pagination returns items, page, page_size, total, and total_pages."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    r = client.get("/api/v1/super-admins/tenants", headers=headers)
    assert r.status_code == 200
    data = r.json()

    assert "items" in data
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 1
    assert data["total_pages"] >= 1
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 20

    # Validate item structure
    first = data["items"][0]
    assert "id" in first
    assert "name" in first
    assert "slug" in first
    assert "is_active" in first
    assert "plan" in first
    assert "subscription_status" in first


def test_p1_list_tenants_custom_page_size_and_ordering(super_admin_fixture):
    """P1: Verify custom page_size, page 2 navigation, and deterministic ordering."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Fetch page 1 with page_size=2
    r1 = client.get("/api/v1/super-admins/tenants?page=1&page_size=2", headers=headers)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert len(d1["items"]) == 2

    # Fetch page 2 with page_size=2
    r2 = client.get("/api/v1/super-admins/tenants?page=2&page_size=2", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["page"] == 2
    assert d2["page_size"] == 2

    # Ensure pages have non-overlapping items (stable ordering)
    p1_ids = {t["id"] for t in d1["items"]}
    p2_ids = {t["id"] for t in d2["items"]}
    assert p1_ids.isdisjoint(p2_ids), f"Page 1 ({p1_ids}) and Page 2 ({p2_ids}) overlapped!"


def test_p1_list_tenants_empty_page_and_max_page_size(super_admin_fixture):
    """P1: Verify empty page behavior and max page_size validation."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Empty page
    r_empty = client.get("/api/v1/super-admins/tenants?page=99999&page_size=20", headers=headers)
    assert r_empty.status_code == 200
    assert r_empty.json()["items"] == []
    assert r_empty.json()["page"] == 99999

    # Max page_size = 100 allowed
    r_max = client.get("/api/v1/super-admins/tenants?page=1&page_size=100", headers=headers)
    assert r_max.status_code == 200
    assert r_max.json()["page_size"] == 100


def test_p1_list_tenants_validation_errors(super_admin_fixture):
    """P1: Verify invalid pagination and filter parameters are rejected with 422."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # page < 1
    assert client.get("/api/v1/super-admins/tenants?page=0", headers=headers).status_code == 422
    assert client.get("/api/v1/super-admins/tenants?page=-5", headers=headers).status_code == 422

    # page_size < 1 or > 100
    assert client.get("/api/v1/super-admins/tenants?page_size=0", headers=headers).status_code == 422
    assert client.get("/api/v1/super-admins/tenants?page_size=101", headers=headers).status_code == 422

    # invalid boolean filter
    assert client.get("/api/v1/super-admins/tenants?is_active=notabool", headers=headers).status_code == 422


def test_p1_list_tenants_search_by_name_and_domain(super_admin_fixture, tenant_fixture):
    """P1: Verify search filters by tenant name and domain case-insensitively."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Search by domain
    domain_frag = tenant_fixture["domain"]
    r_domain = client.get(f"/api/v1/super-admins/tenants?search={domain_frag}", headers=headers)
    assert r_domain.status_code == 200
    data = r_domain.json()
    assert data["total"] >= 1
    assert any(t["id"] == tenant_fixture["tenant_id"] for t in data["items"])

    # Search case-insensitive
    r_upper = client.get(f"/api/v1/super-admins/tenants?search={domain_frag.upper()}", headers=headers)
    assert r_upper.status_code == 200
    assert any(t["id"] == tenant_fixture["tenant_id"] for t in r_upper.json()["items"])

    # Search with no match
    r_none = client.get("/api/v1/super-admins/tenants?search=xyz_completely_nonexistent_token_9999", headers=headers)
    assert r_none.status_code == 200
    assert r_none.json()["total"] == 0
    assert r_none.json()["items"] == []


def test_p1_list_tenants_search_by_admin_email(super_admin_fixture, tenant_fixture):
    """P1: Verify search finds tenant by user admin email (via users correlated EXISTS query)."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    email = tenant_fixture["email"]
    r_email = client.get(f"/api/v1/super-admins/tenants?search={email}", headers=headers)
    assert r_email.status_code == 200
    data = r_email.json()
    assert data["total"] >= 1
    assert any(t["id"] == tenant_fixture["tenant_id"] for t in data["items"])


def test_p1_list_tenants_status_and_plan_filters(super_admin_fixture, tenant_fixture):
    """P1: Verify filtering by is_active, plan, and subscription_status."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Filter is_active=true
    r_active = client.get("/api/v1/super-admins/tenants?is_active=true", headers=headers)
    assert r_active.status_code == 200
    for t in r_active.json()["items"]:
        assert t["is_active"] is True

    # Filter plan=basic
    r_plan = client.get("/api/v1/super-admins/tenants?plan=basic", headers=headers)
    assert r_plan.status_code == 200
    for t in r_plan.json()["items"]:
        assert t["plan"] == "basic"

    # Filter subscription_status=trial
    r_sub = client.get("/api/v1/super-admins/tenants?subscription_status=trial", headers=headers)
    assert r_sub.status_code == 200
    for t in r_sub.json()["items"]:
        assert t["subscription_status"] == "trial"


def test_p1_list_tenants_combined_filters(super_admin_fixture, tenant_fixture):
    """P1: Verify combining search, status, plan, and pagination."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    domain = tenant_fixture["domain"]
    r = client.get(
        f"/api/v1/super-admins/tenants?search={domain}&is_active=true&plan=basic&subscription_status=trial&page=1&page_size=10",
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(t["id"] == tenant_fixture["tenant_id"] for t in data["items"])


def test_p1_list_tenants_unauthorized_access(tenant_fixture):
    """P1: Verify anonymous and tenant users cannot access GET /api/v1/super-admins/tenants."""
    # Anonymous
    r_anon = client.get("/api/v1/super-admins/tenants")
    assert r_anon.status_code == 401

    # Tenant user
    headers = {"Authorization": f"Bearer {tenant_fixture['token']}"}
    r_tenant = client.get("/api/v1/super-admins/tenants", headers=headers)
    assert r_tenant.status_code == 401


def test_p1_get_tenant_detail_success(super_admin_fixture, tenant_fixture):
    """P1: Verify GET /api/v1/super-admins/tenants/{tenant_id} returns enriched overview."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    tenant_id = tenant_fixture["tenant_id"]
    r = client.get(f"/api/v1/super-admins/tenants/{tenant_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()

    # Verify basic tenant information
    assert data["id"] == tenant_id
    assert data["name"] == tenant_fixture["name"]
    assert data["slug"] == tenant_fixture["domain"]
    assert data["is_active"] is True
    assert data["plan"] == "basic"
    assert data["subscription_status"] == "trial"

    # Verify owner/admin information
    assert data["owner"] is not None
    assert data["owner"]["email"] == tenant_fixture["email"]
    assert data["owner"]["is_active"] is True
    assert "id" in data["owner"]
    assert "full_name" in data["owner"]

    # Verify user counts
    assert data["total_users"] >= 1
    assert data["active_users"] >= 1

    # Verify store counts structure
    assert "total_stores" in data
    assert "active_stores" in data
    assert isinstance(data["stores"], list)


def test_p1_get_tenant_detail_not_found(super_admin_fixture):
    """P1: Verify 404 for non-existent tenant ID."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    r = client.get("/api/v1/super-admins/tenants/999999", headers=headers)
    assert r.status_code == 404


def test_p1_get_tenant_detail_unauthorized(tenant_fixture):
    """P1: Verify anonymous and tenant users cannot access tenant detail endpoint."""
    tenant_id = tenant_fixture["tenant_id"]

    # Anonymous
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}").status_code == 401

    # Tenant user
    headers = {"Authorization": f"Bearer {tenant_fixture['token']}"}
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}", headers=headers).status_code == 401


def test_p1_get_tenant_detail_store_and_user_counts(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify store and active store counts, staff counts, and store list summary."""
    from app.models.store import Store

    tenant_id = tenant_fixture["tenant_id"]

    # Insert one active store and one inactive store for this tenant
    s1 = Store(tenant_id=tenant_id, name="Main Store", code=f"STR1_{uuid.uuid4().hex[:4]}", is_main=True, is_active=True)
    s2 = Store(tenant_id=tenant_id, name="Branch Store", code=f"STR2_{uuid.uuid4().hex[:4]}", is_main=False, is_active=False)
    db_session.add_all([s1, s2])
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    r = client.get(f"/api/v1/super-admins/tenants/{tenant_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()

    assert data["total_stores"] == 2
    assert data["active_stores"] == 1
    assert len(data["stores"]) == 2
    # Verify concise summary fields
    first_store = data["stores"][0]
    assert "id" in first_store
    assert "name" in first_store
    assert "code" in first_store
    assert "is_main" in first_store
    assert "is_active" in first_store


def test_p1_get_tenant_detail_no_cross_tenant_leakage(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify tenant detail counts and stores do not leak across tenants."""
    from app.models.store import Store

    tenant_id = tenant_fixture["tenant_id"]

    # Create another tenant
    uid2 = uuid.uuid4().hex[:6]
    reg2 = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": f"Other Tenant {uid2}",
            "domain": f"oth-{uid2}",
            "email": f"other_admin_{uid2}@example.com",
            "admin_name": f"Other Admin {uid2}",
            "password": "OtherPassword@123!",
            "phone": f"91{uuid.uuid4().int % 100000000:08d}",
        },
    )
    other_tenant_id = reg2.json()["tenant_id"]

    # Add 3 stores to other tenant
    other_stores = [
        Store(tenant_id=other_tenant_id, name=f"Other Store {i}", is_main=(i == 0), is_active=True)
        for i in range(3)
    ]
    db_session.add_all(other_stores)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Query first tenant: must not see other tenant's stores
    r1 = client.get(f"/api/v1/super-admins/tenants/{tenant_id}", headers=headers)
    assert r1.status_code == 200
    d1 = r1.json()

    # Query other tenant: must see exactly its own 3 stores
    r2 = client.get(f"/api/v1/super-admins/tenants/{other_tenant_id}", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()

    assert d2["total_stores"] == 3
    assert d2["active_stores"] == 3
    assert all(s["id"] not in {st["id"] for st in d1["stores"]} for s in d2["stores"])


def test_p1_list_tenant_users_default_pagination(super_admin_fixture, tenant_fixture):
    """P1: Verify default pagination returns items, page, page_size, total, and total_pages."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    tenant_id = tenant_fixture["tenant_id"]
    r = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users", headers=headers)
    assert r.status_code == 200
    data = r.json()

    assert "items" in data
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 1
    assert data["total_pages"] >= 1
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1

    first = data["items"][0]
    assert first["tenant_id"] == tenant_id
    assert "email" in first
    assert "full_name" in first
    assert "is_active" in first
    assert "role" in first


def test_p1_list_tenant_users_unauthorized(tenant_fixture):
    """P1: Verify anonymous and tenant users cannot access tenant user directory."""
    tenant_id = tenant_fixture["tenant_id"]

    # Anonymous
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users").status_code == 401

    # Tenant user
    headers = {"Authorization": f"Bearer {tenant_fixture['token']}"}
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users", headers=headers).status_code == 401


def test_p1_list_tenant_users_not_found(super_admin_fixture):
    """P1: Verify 404 for non-existent tenant ID."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    assert client.get("/api/v1/super-admins/tenants/999999/users", headers=headers).status_code == 404


def test_p1_list_tenant_users_pagination_and_validation(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify page navigation, boundaries, and validation errors."""
    from app.models.user import User
    from app.models.role import Role
    from app.core.security import get_password_hash

    tenant_id = tenant_fixture["tenant_id"]

    # Fetch admin role for this tenant
    role = db_session.query(Role).filter(Role.tenant_id == tenant_id).first()

    # Add 2 additional active users
    u1 = User(tenant_id=tenant_id, role_id=role.id, email=f"user1_{uuid.uuid4().hex[:6]}@example.com", password_hash=get_password_hash("Pass@123!"), full_name="User Alpha", is_active=True, is_deleted=False)
    u2 = User(tenant_id=tenant_id, role_id=role.id, email=f"user2_{uuid.uuid4().hex[:6]}@example.com", password_hash=get_password_hash("Pass@123!"), full_name="User Beta", is_active=True, is_deleted=False)
    db_session.add_all([u1, u2])
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Page 1 with page_size=2
    r1 = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page=1&page_size=2", headers=headers)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert len(d1["items"]) == 2

    # Page 2 with page_size=2
    r2 = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page=2&page_size=2", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["page"] == 2
    assert d2["page_size"] == 2
    assert len(d2["items"]) >= 1

    # Disjoint pages (stable ordering)
    p1_ids = {u["id"] for u in d1["items"]}
    p2_ids = {u["id"] for u in d2["items"]}
    assert p1_ids.isdisjoint(p2_ids)

    # Empty page
    r_empty = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page=99999&page_size=20", headers=headers)
    assert r_empty.status_code == 200
    assert r_empty.json()["items"] == []

    # Validation
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page=0", headers=headers).status_code == 422
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page_size=0", headers=headers).status_code == 422
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page_size=101", headers=headers).status_code == 422
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?is_active=notabool", headers=headers).status_code == 422


def test_p1_list_tenant_users_search_and_filters(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify searching by name, email, and filtering by role and status."""
    from app.models.user import User
    from app.models.role import Role
    from app.core.security import get_password_hash

    tenant_id = tenant_fixture["tenant_id"]

    # Roles for this tenant
    admin_role = db_session.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "admin").first()
    staff_role = db_session.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "staff").first()

    unique_token = uuid.uuid4().hex[:6]
    u_staff = User(
        tenant_id=tenant_id,
        role_id=staff_role.id,
        email=f"special_staff_{unique_token}@example.com",
        password_hash=get_password_hash("Pass@123!"),
        full_name=f"Unique Staff Member {unique_token}",
        phone="9871112233",
        is_active=False,
        is_deleted=False,
    )
    db_session.add(u_staff)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # 1. Search by unique full_name
    r_search = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?search={unique_token}", headers=headers)
    assert r_search.status_code == 200
    assert r_search.json()["total"] == 1
    assert r_search.json()["items"][0]["id"] == u_staff.id

    # 2. Filter by role=staff
    r_staff = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?role=staff", headers=headers)
    assert r_staff.status_code == 200
    for item in r_staff.json()["items"]:
        assert item["role"] == "staff"

    # 3. Filter by is_active=false
    r_inactive = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?is_active=false", headers=headers)
    assert r_inactive.status_code == 200
    assert any(item["id"] == u_staff.id for item in r_inactive.json()["items"])
    for item in r_inactive.json()["items"]:
        assert item["is_active"] is False


def test_p1_list_tenant_users_soft_delete_and_isolation(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify soft-deleted users are excluded and other tenant users never appear."""
    from app.models.user import User
    from app.models.role import Role
    from app.core.security import get_password_hash

    tenant_id = tenant_fixture["tenant_id"]
    admin_role = db_session.query(Role).filter(Role.tenant_id == tenant_id).first()

    # Create soft-deleted user for this tenant
    del_token = uuid.uuid4().hex[:6]
    u_deleted = User(
        tenant_id=tenant_id,
        role_id=admin_role.id,
        email=f"deleted_{del_token}@example.com",
        password_hash=get_password_hash("Pass@123!"),
        full_name="Deleted User",
        is_active=True,
        is_deleted=True,  # SOFT DELETED!
    )
    db_session.add(u_deleted)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Verify soft-deleted user is NOT returned
    r_list = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?search={del_token}", headers=headers)
    assert r_list.status_code == 200
    assert r_list.json()["total"] == 0
    assert r_list.json()["items"] == []

    # Verify tenant isolation: all items returned have tenant_id == tenant_id
    r_all = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/users?page_size=100", headers=headers)
    assert r_all.status_code == 200
    for u in r_all.json()["items"]:
        assert u["tenant_id"] == tenant_id


def test_p1_list_tenant_stores_default_pagination(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify default pagination returns items, page, page_size, total, and total_pages for stores."""
    from app.models.store import Store

    tenant_id = tenant_fixture["tenant_id"]

    # Ensure at least 1 store exists
    store = Store(
        tenant_id=tenant_id,
        name="Flagship Retail Store",
        code=f"FLG_{uuid.uuid4().hex[:4]}",
        city="Mumbai",
        state="Maharashtra",
        is_main=True,
        is_active=True,
    )
    db_session.add(store)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    r = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores", headers=headers)
    assert r.status_code == 200
    data = r.json()

    assert "items" in data
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 1
    assert data["total_pages"] >= 1
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1

    first = data["items"][0]
    assert first["tenant_id"] == tenant_id
    assert "name" in first
    assert "code" in first
    assert "city" in first
    assert "state" in first
    assert "is_main" in first
    assert "is_active" in first
    assert "created_at" in first


def test_p1_list_tenant_stores_unauthorized(tenant_fixture):
    """P1: Verify anonymous and tenant users cannot access tenant store directory."""
    tenant_id = tenant_fixture["tenant_id"]

    # Anonymous
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores").status_code == 401

    # Tenant user
    headers = {"Authorization": f"Bearer {tenant_fixture['token']}"}
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores", headers=headers).status_code == 401


def test_p1_list_tenant_stores_not_found(super_admin_fixture):
    """P1: Verify 404 for non-existent tenant ID."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    assert client.get("/api/v1/super-admins/tenants/999999/stores", headers=headers).status_code == 404


def test_p1_list_tenant_stores_pagination_and_validation(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify store page navigation, boundaries, and validation errors."""
    from app.models.store import Store

    tenant_id = tenant_fixture["tenant_id"]

    # Add 3 stores
    s1 = Store(tenant_id=tenant_id, name="Store 1", code=f"S1_{uuid.uuid4().hex[:4]}", is_main=True, is_active=True)
    s2 = Store(tenant_id=tenant_id, name="Store 2", code=f"S2_{uuid.uuid4().hex[:4]}", is_main=False, is_active=True)
    s3 = Store(tenant_id=tenant_id, name="Store 3", code=f"S3_{uuid.uuid4().hex[:4]}", is_main=False, is_active=False)
    db_session.add_all([s1, s2, s3])
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Page 1 with page_size=2
    r1 = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page=1&page_size=2", headers=headers)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert len(d1["items"]) == 2

    # Page 2 with page_size=2
    r2 = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page=2&page_size=2", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["page"] == 2
    assert d2["page_size"] == 2
    assert len(d2["items"]) >= 1

    # Disjoint pages (stable ordering)
    p1_ids = {s["id"] for s in d1["items"]}
    p2_ids = {s["id"] for s in d2["items"]}
    assert p1_ids.isdisjoint(p2_ids)

    # Empty page
    r_empty = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page=99999&page_size=20", headers=headers)
    assert r_empty.status_code == 200
    assert r_empty.json()["items"] == []

    # Validation
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page=0", headers=headers).status_code == 422
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page_size=0", headers=headers).status_code == 422
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page_size=101", headers=headers).status_code == 422
    assert client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?is_active=notabool", headers=headers).status_code == 422


def test_p1_list_tenant_stores_search_and_filters(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify searching by name, code, and filtering by is_main, is_active, city, state."""
    from app.models.store import Store

    tenant_id = tenant_fixture["tenant_id"]

    unique_token = uuid.uuid4().hex[:6]
    store = Store(
        tenant_id=tenant_id,
        name=f"Special Outlet {unique_token}",
        code=f"OUT_{unique_token}",
        city="Bengaluru",
        state="Karnataka",
        phone="9876500000",
        email=f"outlet_{unique_token}@example.com",
        is_main=True,
        is_active=False,
    )
    db_session.add(store)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # 1. Search by unique token (in name/code)
    r_search = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?search={unique_token}", headers=headers)
    assert r_search.status_code == 200
    assert r_search.json()["total"] == 1
    assert r_search.json()["items"][0]["id"] == store.id

    # 2. Filter by is_main=true
    r_main = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?is_main=true", headers=headers)
    assert r_main.status_code == 200
    for s in r_main.json()["items"]:
        assert s["is_main"] is True

    # 3. Filter by is_active=false
    r_inactive = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?is_active=false", headers=headers)
    assert r_inactive.status_code == 200
    assert any(s["id"] == store.id for s in r_inactive.json()["items"])
    for s in r_inactive.json()["items"]:
        assert s["is_active"] is False

    # 4. Filter by city=Bengaluru
    r_city = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?city=Bengaluru", headers=headers)
    assert r_city.status_code == 200
    for s in r_city.json()["items"]:
        assert s["city"] == "Bengaluru"

    # 5. Filter by state=Karnataka
    r_state = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?state=Karnataka", headers=headers)
    assert r_state.status_code == 200
    for s in r_state.json()["items"]:
        assert s["state"] == "Karnataka"


def test_p1_list_tenant_stores_isolation(super_admin_fixture, tenant_fixture, db_session):
    """P1: Verify tenant store isolation: stores belonging to another tenant never appear."""
    from app.models.store import Store

    tenant_id = tenant_fixture["tenant_id"]

    # Register second tenant
    uid2 = uuid.uuid4().hex[:6]
    reg2 = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": f"Isolated Tenant {uid2}",
            "domain": f"iso-{uid2}",
            "email": f"isolated_admin_{uid2}@example.com",
            "admin_name": f"Isolated Admin {uid2}",
            "password": "IsoPassword@123!",
            "phone": f"91{uuid.uuid4().int % 100000000:08d}",
        },
    )
    other_tenant_id = reg2.json()["tenant_id"]

    # Add store to other tenant
    other_store = Store(
        tenant_id=other_tenant_id,
        name="Other Secret Store",
        code=f"SEC_{uuid.uuid4().hex[:4]}",
        is_main=True,
        is_active=True,
    )
    db_session.add(other_store)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Query first tenant: other_store MUST NOT appear
    r1 = client.get(f"/api/v1/super-admins/tenants/{tenant_id}/stores?page_size=100", headers=headers)
    assert r1.status_code == 200
    t1_store_ids = {s["id"] for s in r1.json()["items"]}
    assert other_store.id not in t1_store_ids
    for s in r1.json()["items"]:
        assert s["tenant_id"] == tenant_id

    # Query other tenant: returns strictly its own store
    r2 = client.get(f"/api/v1/super-admins/tenants/{other_tenant_id}/stores", headers=headers)
    assert r2.status_code == 200
    t2_store_ids = {s["id"] for s in r2.json()["items"]}
    assert other_store.id in t2_store_ids
    for s in r2.json()["items"]:
        assert s["tenant_id"] == other_tenant_id


# ==============================================================================
# P1: SUPER ADMIN DIRECTORY TESTS (GET /api/v1/super-admins)
# ==============================================================================

def test_p1_list_super_admins_default_pagination(super_admin_fixture):
    """P1: Verify GET /api/v1/super-admins returns paginated response with standard wrapper."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    r = client.get("/api/v1/super-admins", headers=headers)
    assert r.status_code == 200
    data = r.json()

    assert "items" in data
    assert "page" in data
    assert "page_size" in data
    assert "total" in data
    assert "total_pages" in data

    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 1
    assert data["total_pages"] >= 1
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1

    # Check safe fields of super admin item
    sa_emails = [item["email"] for item in data["items"]]
    assert super_admin_fixture["email"] in sa_emails

    item = next(i for i in data["items"] if i["email"] == super_admin_fixture["email"])
    assert "id" in item
    assert "email" in item
    assert "full_name" in item
    assert "phone" in item
    assert "is_active" in item
    assert "created_at" in item
    assert "updated_at" in item


def test_p1_list_super_admins_unauthorized(tenant_fixture):
    """P1: Verify anonymous and tenant user requests to GET /api/v1/super-admins are rejected with 401."""
    # 1. Anonymous request
    r_anon = client.get("/api/v1/super-admins")
    assert r_anon.status_code == 401

    # 2. Tenant user token
    login_r = client.post(
        "/api/v1/auth/login",
        json={
            "email": tenant_fixture["email"],
            "password": tenant_fixture["password"],
        },
    )
    tenant_token = login_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {tenant_token}"}

    r_tenant = client.get("/api/v1/super-admins", headers=headers)
    assert r_tenant.status_code == 401


def test_p1_list_super_admins_pagination_and_validation(super_admin_fixture, db_session):
    """P1: Verify custom page size, page bounds, and parameter validation for Super Admin directory."""
    from app.core.security import get_password_hash

    # Seed 3 extra super admins
    for i in range(3):
        extra_sa = SuperAdmin(
            email=f"seeded_extra_sa_{uuid.uuid4().hex[:6]}@example.com",
            full_name=f"Extra Admin {i}",
            hashed_password=get_password_hash("ExtraAdmin@123!"),
            phone=f"98{uuid.uuid4().int % 100000000:08d}",
            is_active=True,
        )
        db_session.add(extra_sa)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # 1. Page size = 2
    r_p2 = client.get("/api/v1/super-admins?page=1&page_size=2", headers=headers)
    assert r_p2.status_code == 200
    data_p2 = r_p2.json()
    assert len(data_p2["items"]) == 2
    assert data_p2["page_size"] == 2
    assert data_p2["total_pages"] >= 2

    # 2. Page 2 with page size = 2
    r_page2 = client.get("/api/v1/super-admins?page=2&page_size=2", headers=headers)
    assert r_page2.status_code == 200
    data_page2 = r_page2.json()
    assert len(data_page2["items"]) == 2
    # Ensure distinct items
    p1_ids = {item["id"] for item in data_p2["items"]}
    p2_ids = {item["id"] for item in data_page2["items"]}
    assert p1_ids.isdisjoint(p2_ids)

    # 3. Out-of-bounds page returns empty items list
    r_empty = client.get("/api/v1/super-admins?page=99999&page_size=20", headers=headers)
    assert r_empty.status_code == 200
    assert r_empty.json()["items"] == []
    assert r_empty.json()["page"] == 99999
    assert r_empty.json()["total"] >= 4

    # 4. Validation errors
    assert client.get("/api/v1/super-admins?page=0", headers=headers).status_code == 422
    assert client.get("/api/v1/super-admins?page=-1", headers=headers).status_code == 422
    assert client.get("/api/v1/super-admins?page_size=0", headers=headers).status_code == 422
    assert client.get("/api/v1/super-admins?page_size=101", headers=headers).status_code == 422
    assert client.get("/api/v1/super-admins?is_active=notabool", headers=headers).status_code == 422


def test_p1_list_super_admins_search_and_filters(super_admin_fixture, db_session):
    """P1: Verify database-level search by full_name, email, phone and filtering by is_active."""
    from app.core.security import get_password_hash

    tag = uuid.uuid4().hex[:6]
    sa_active = SuperAdmin(
        email=f"alpha_officer_{tag}@platformsa.com",
        full_name=f"Alpha Officer {tag}",
        hashed_password=get_password_hash("SecretPassword@123!"),
        phone="9811001100",
        is_active=True,
    )
    sa_inactive = SuperAdmin(
        email=f"beta_director_{tag}@platformsa.com",
        full_name=f"Beta Director {tag}",
        hashed_password=get_password_hash("SecretPassword@123!"),
        phone="9822002200",
        is_active=False,
    )
    db_session.add(sa_active)
    db_session.add(sa_inactive)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # 1. Search by full_name (case-insensitive)
    r_name = client.get(f"/api/v1/super-admins?search=alpha+officer+{tag}", headers=headers)
    assert r_name.status_code == 200
    items = r_name.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == f"alpha_officer_{tag}@platformsa.com"

    # 2. Search case-insensitive uppercase
    r_upper = client.get(f"/api/v1/super-admins?search=ALPHA+OFFICER+{tag.upper()}", headers=headers)
    assert r_upper.status_code == 200
    assert len(r_upper.json()["items"]) == 1

    # 3. Search by email fragment
    r_email = client.get(f"/api/v1/super-admins?search=beta_director_{tag}", headers=headers)
    assert r_email.status_code == 200
    assert len(r_email.json()["items"]) == 1
    assert r_email.json()["items"][0]["full_name"] == f"Beta Director {tag}"

    # 4. Search by phone
    r_phone = client.get("/api/v1/super-admins?search=9822002200", headers=headers)
    assert r_phone.status_code == 200
    matching_phones = [i["phone"] for i in r_phone.json()["items"]]
    assert "9822002200" in matching_phones

    # 5. Search non-existent
    r_none = client.get(f"/api/v1/super-admins?search=nonexistent_token_xyz_{tag}", headers=headers)
    assert r_none.status_code == 200
    assert r_none.json()["total"] == 0
    assert r_none.json()["items"] == []

    # 6. Filter by is_active=true
    r_act = client.get("/api/v1/super-admins?is_active=true&page_size=100", headers=headers)
    assert r_act.status_code == 200
    for i in r_act.json()["items"]:
        assert i["is_active"] is True
    act_emails = {i["email"] for i in r_act.json()["items"]}
    assert sa_active.email in act_emails
    assert sa_inactive.email not in act_emails

    # 7. Filter by is_active=false
    r_inact = client.get("/api/v1/super-admins?is_active=false&page_size=100", headers=headers)
    assert r_inact.status_code == 200
    for i in r_inact.json()["items"]:
        assert i["is_active"] is False
    inact_emails = {i["email"] for i in r_inact.json()["items"]}
    assert sa_inactive.email in inact_emails
    assert sa_active.email not in inact_emails


def test_p1_list_super_admins_combined_and_ordering(super_admin_fixture, db_session):
    """P1: Verify combined search + filter + pagination and deterministic created_at DESC, id DESC ordering."""
    from app.core.security import get_password_hash

    tag = uuid.uuid4().hex[:6]
    sa_x = SuperAdmin(
        email=f"combo_active_{tag}@platformsa.com",
        full_name=f"Combo Specialist {tag}",
        hashed_password=get_password_hash("SecretPassword@123!"),
        phone="9833003300",
        is_active=True,
    )
    sa_y = SuperAdmin(
        email=f"combo_inactive_{tag}@platformsa.com",
        full_name=f"Combo Specialist {tag}",
        hashed_password=get_password_hash("SecretPassword@123!"),
        phone="9844004400",
        is_active=False,
    )
    db_session.add(sa_x)
    db_session.add(sa_y)
    db_session.commit()

    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    # Combined: search="Combo Specialist <tag>" AND is_active=true
    r_comb_act = client.get(
        f"/api/v1/super-admins?search=Combo+Specialist+{tag}&is_active=true",
        headers=headers,
    )
    assert r_comb_act.status_code == 200
    assert r_comb_act.json()["total"] == 1
    assert r_comb_act.json()["items"][0]["email"] == f"combo_active_{tag}@platformsa.com"

    # Combined: search="Combo Specialist <tag>" AND is_active=false
    r_comb_inact = client.get(
        f"/api/v1/super-admins?search=Combo+Specialist+{tag}&is_active=false",
        headers=headers,
    )
    assert r_comb_inact.status_code == 200
    assert r_comb_inact.json()["total"] == 1
    assert r_comb_inact.json()["items"][0]["email"] == f"combo_inactive_{tag}@platformsa.com"

    # Verify deterministic ordering: created_at DESC, id DESC
    r_all = client.get("/api/v1/super-admins?page_size=100", headers=headers)
    assert r_all.status_code == 200
    items = r_all.json()["items"]
    assert len(items) >= 2
    for idx in range(len(items) - 1):
        curr_dt = items[idx]["created_at"]
        next_dt = items[idx + 1]["created_at"]
        curr_id = items[idx]["id"]
        next_id = items[idx + 1]["id"]
        assert (curr_dt > next_dt) or (curr_dt == next_dt and curr_id >= next_id)


def test_p1_list_super_admins_security_no_sensitive_fields(super_admin_fixture):
    """P1: Verify response serialization strictly omits hashed_password, tokens, passwords, and secrets."""
    login_r = client.post(
        "/api/v1/super-admins/login",
        json={
            "email": super_admin_fixture["email"],
            "password": super_admin_fixture["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login_r.json()['access_token']}"}

    r = client.get("/api/v1/super-admins?page_size=50", headers=headers)
    assert r.status_code == 200
    data = r.json()

    forbidden_keys = {
        "hashed_password",
        "password",
        "access_token",
        "refresh_token",
        "token",
        "secret",
        "secret_key",
        "credentials",
        "reset_token",
    }

    assert len(data["items"]) >= 1
    for item in data["items"]:
        # Verify no forbidden keys in dictionary
        present_forbidden = forbidden_keys.intersection(item.keys())
        assert not present_forbidden, f"Sensitive keys exposed in response: {present_forbidden}"
        # Verify only safe white-listed fields are exposed
        expected_keys = {"id", "email", "full_name", "phone", "is_active", "created_at", "updated_at"}
        assert set(item.keys()) == expected_keys




