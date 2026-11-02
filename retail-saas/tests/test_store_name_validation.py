import uuid
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.store import StoreCreate, StoreUpdate

client = TestClient(app)


@pytest.fixture(scope="module")
def tenant_auth():
    suffix = uuid.uuid4().hex[:6]
    slug = f"stname-{suffix}"
    email = f"owner_{suffix}@testname.com"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Main Outlet {suffix}",
            "domain": slug,
            "owner_email": email,
            "owner_name": "Store Owner",
            "password": "Password@123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_res.status_code == 200, f"Register failed: {reg_res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password@123!"},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}}


# =========================================================================
# 1. Direct Schema Validation Unit Tests (StoreCreate & StoreUpdate)
# =========================================================================

@pytest.mark.parametrize(
    "valid_name",
    [
        "Om",
        "Sai",
        "Riya Boutique",
        "Sai Krupa Traders",
        "Main Retail Store",
        "  Om  ",
        "  Sai Krupa Traders  ",
    ],
)
def test_schema_valid_store_names(valid_name):
    # StoreCreate
    create_schema = StoreCreate(name=valid_name)
    assert create_schema.name == valid_name.strip()

    # StoreUpdate
    update_schema = StoreUpdate(name=valid_name)
    assert update_schema.name == valid_name.strip()


@pytest.mark.parametrize(
    "invalid_name",
    [
        "O",
        "A",
        "AB",
        "ab",
        "@#$%^&*",
        "Store@123",
        "Sai#Store",
        "   ",
        "",
    ],
)
def test_schema_invalid_store_names_rejected(invalid_name):
    # StoreCreate must reject
    with pytest.raises(ValidationError):
        StoreCreate(name=invalid_name)

    # StoreUpdate must reject
    with pytest.raises(ValidationError):
        StoreUpdate(name=invalid_name)


def test_schema_none_name_allowed_in_store_update():
    update_schema = StoreUpdate(name=None)
    assert update_schema.name is None


# =========================================================================
# 2. Integration Tests: Add Store (POST /api/v1/stores/)
# =========================================================================

def test_add_store_valid_names(tenant_auth):
    headers = tenant_auth["headers"]

    valid_names = [
        "Om",
        "Sai",
        "Riya Boutique",
        "Sai Krupa Traders",
        "Main Retail Store",
    ]

    for name in valid_names:
        res = client.post(
            "/api/v1/stores/",
            headers=headers,
            json={
                "name": name,
                "code": f"C{uuid.uuid4().hex[:5].upper()}",
            },
        )
        assert res.status_code == 201, f"Failed for valid name '{name}': {res.text}"
        data = res.json()
        assert data["name"] == name


@pytest.mark.parametrize(
    "invalid_name",
    [
        "O",
        "A",
        "AB",
        "@#$%^&*",
        "Store@123",
        "Sai#Store",
        "   ",
        "",
    ],
)
def test_add_store_invalid_names_rejected(tenant_auth, invalid_name):
    headers = tenant_auth["headers"]

    res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={
            "name": invalid_name,
            "code": f"C{uuid.uuid4().hex[:5].upper()}",
        },
    )
    assert res.status_code == 422, f"Expected 422 for '{invalid_name}', got {res.status_code}: {res.text}"


# =========================================================================
# 3. Integration Tests: Update Store (PATCH /api/v1/stores/{store_id})
# =========================================================================

def test_update_store_name_validation(tenant_auth):
    headers = tenant_auth["headers"]

    # Create initial store
    create_res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={
            "name": "Initial Store Name",
            "code": f"C{uuid.uuid4().hex[:5].upper()}",
        },
    )
    assert create_res.status_code == 201, create_res.text
    store_id = create_res.json()["id"]

    # 1. Update to valid name "Sai Krupa Traders Update"
    upd_res = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "Sai Krupa Traders Update"},
    )
    assert upd_res.status_code == 200, upd_res.text
    assert upd_res.json()["name"] == "Sai Krupa Traders Update"

    # 2. Update to valid short 2-letter name "Go"
    upd_res_om = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "Go"},
    )
    assert upd_res_om.status_code == 200, upd_res_om.text
    assert upd_res_om.json()["name"] == "Go"

    # 3. Update to invalid single-letter name "O" -> 422
    upd_fail_o = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "O"},
    )
    assert upd_fail_o.status_code == 422, upd_fail_o.text

    # 4. Update to invalid abbreviation "AB" -> 422
    upd_fail_ab = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "AB"},
    )
    assert upd_fail_ab.status_code == 422, upd_fail_ab.text

    # 5. Update with special characters "Store@123" -> 422
    upd_fail_spec = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "Store@123"},
    )
    assert upd_fail_spec.status_code == 422, upd_fail_spec.text

    # 6. Update with special characters "Sai#Store" -> 422
    upd_fail_hash = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "Sai#Store"},
    )
    assert upd_fail_hash.status_code == 422, upd_fail_hash.text

    # 7. Update with only special characters "@#$%^&*" -> 422
    upd_fail_chars = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "@#$%^&*"},
    )
    assert upd_fail_chars.status_code == 422, upd_fail_chars.text

    # 8. Update with whitespace only "   " -> 422
    upd_fail_space = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "   "},
    )
    assert upd_fail_space.status_code == 422, upd_fail_space.text
