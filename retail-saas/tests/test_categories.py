import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.category import Category
from app.models.product import Product

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"cat-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Category Admin",
            "password": "Password123!",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    from app.models.user import User
    user = db.query(User).filter(User.email == email).first()
    tenant_id = user.tenant_id
    db.close()

    return {"headers": headers, "tenant_id": tenant_id}


# =====================================================================
# 1. GET /api/v1/categories
# =====================================================================

def test_list_categories_empty_returns_wrapper(tenant_fixture):
    headers = tenant_fixture["headers"]
    resp = client.get("/api/v1/categories", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "No categories found"
    assert body["data"] == []


def test_list_categories_with_data_and_tenant_isolation(tenant_fixture):
    headers_a = tenant_fixture["headers"]
    tenant_id_a = tenant_fixture["tenant_id"]

    # Create category for Tenant A
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Beverages", "description": "Tea, coffee, juices"},
        headers=headers_a,
    )
    assert create_resp.status_code == 201, create_resp.text
    cat_a = create_resp.json()

    # List categories for Tenant A
    resp_a = client.get("/api/v1/categories", headers=headers_a)
    assert resp_a.status_code == 200
    body_a = resp_a.json()
    assert body_a["success"] is True
    assert body_a["message"] == "Categories retrieved successfully"
    assert len(body_a["data"]) >= 1
    assert any(c["id"] == cat_a["id"] for c in body_a["data"])

    # Register Tenant B
    slug_b = f"catb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Tenant B should NOT see Tenant A's category
    resp_b = client.get("/api/v1/categories", headers=headers_b)
    assert resp_b.status_code == 200
    body_b = resp_b.json()
    assert body_b["success"] is True
    assert not any(c["id"] == cat_a["id"] for c in body_b["data"])


# =====================================================================
# 2. POST /api/v1/categories
# =====================================================================

def test_create_category_valid_names(tenant_fixture):
    headers = tenant_fixture["headers"]
    valid_names = [
        "Beverages",
        "Personal Care Products",
        "Electronic Induction Cooker",
        "Fresh Fruits",
        "Dairy Products",
        "Home Appliances",
        "4K TVs",
        "USB-C Accessories",
        "Shoes 2026",
    ]
    for name in valid_names:
        resp = client.post(
            "/api/v1/categories",
            json={"name": name, "description": "Valid description for testing"},
            headers=headers,
        )
        assert resp.status_code == 201, f"Failed for name: {name}, error: {resp.text}"
        data = resp.json()
        assert data["name"] == name
        assert data["id"] > 0
        assert data["tenant_id"] == tenant_fixture["tenant_id"]


def test_create_category_reject_invalid_names(tenant_fixture):
    headers = tenant_fixture["headers"]
    invalid_names = [
        "",
        "   ",
        "string",
        "null",
        "none",
        "undefined",
        "----",
        "---",
        "- - -",
        "1234",
        "999",
        "@#$%^",
        "!@#$%",
        "test",
        "sample",
    ]
    for name in invalid_names:
        resp = client.post(
            "/api/v1/categories",
            json={"name": name, "description": "Some description"},
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for invalid name '{name}', got {resp.status_code}"

    # Test null name
    resp_null = client.post(
        "/api/v1/categories",
        json={"name": None, "description": "Some description"},
        headers=headers,
    )
    assert resp_null.status_code == 422


def test_create_category_description_validation(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Valid descriptions
    valid_descs = [
        "Fresh beverages and soft drinks",
        "Daily household and personal care products",
        "Kitchen appliances and cooking equipment",
    ]
    for desc in valid_descs:
        resp = client.post(
            "/api/v1/categories",
            json={"name": f"Cat {uuid.uuid4().hex[:6]}", "description": desc},
            headers=headers,
        )
        assert resp.status_code == 201, f"Failed for valid desc: {desc}"

    # Invalid descriptions
    invalid_descs = [
        "",
        "   ",
        "string",
        "null",
        "none",
        "undefined",
        "----",
        "@#$%^",
        "1234",
    ]
    for desc in invalid_descs:
        resp = client.post(
            "/api/v1/categories",
            json={"name": f"Cat {uuid.uuid4().hex[:6]}", "description": desc},
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for invalid desc '{desc}', got {resp.status_code}"


def test_create_category_parent_validation(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Invalid parent_id values (0, negative, float, string) -> 422
    assert client.post("/api/v1/categories", json={"name": "Subcat", "parent_id": 0}, headers=headers).status_code == 422
    assert client.post("/api/v1/categories", json={"name": "Subcat", "parent_id": -5}, headers=headers).status_code == 422
    assert client.post("/api/v1/categories", json={"name": "Subcat", "parent_id": 1.5}, headers=headers).status_code == 422
    assert client.post("/api/v1/categories", json={"name": "Subcat", "parent_id": "abc"}, headers=headers).status_code == 422

    # Non-existing parent_id -> 404
    resp_nonexistent = client.post(
        "/api/v1/categories",
        json={"name": "Subcat", "parent_id": 999999},
        headers=headers,
    )
    assert resp_nonexistent.status_code == 404

    # Valid parent_id -> 201
    parent_resp = client.post(
        "/api/v1/categories",
        json={"name": "Parent Category"},
        headers=headers,
    )
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]

    child_resp = client.post(
        "/api/v1/categories",
        json={"name": "Child Category", "parent_id": parent_id},
        headers=headers,
    )
    assert child_resp.status_code == 201
    assert child_resp.json()["parent_id"] == parent_id


def test_create_category_cross_tenant_parent(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    # Register Tenant B
    slug_b = f"catb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Tenant B creates a category
    cat_b = client.post(
        "/api/v1/categories",
        json={"name": "Tenant B Parent"},
        headers=headers_b,
    ).json()

    # Tenant A attempts to use Tenant B's category as parent -> 404
    resp_cross = client.post(
        "/api/v1/categories",
        json={"name": "Tenant A Child", "parent_id": cat_b["id"]},
        headers=headers_a,
    )
    assert resp_cross.status_code == 404


# =====================================================================
# 3. GET /api/v1/categories/{category_id}
# =====================================================================

def test_get_category_by_id_valid(tenant_fixture):
    headers = tenant_fixture["headers"]
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Electronics", "description": "Gadgets and tech"},
        headers=headers,
    )
    cat_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/categories/{cat_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == cat_id
    assert data["name"] == "Electronics"
    assert data["description"] == "Gadgets and tech"


def test_get_category_by_id_validation(tenant_fixture):
    headers = tenant_fixture["headers"]

    # category_id = 0 -> 422
    assert client.get("/api/v1/categories/0", headers=headers).status_code == 422

    # negative ID -> 422
    assert client.get("/api/v1/categories/-1", headers=headers).status_code == 422

    # decimal ID -> 422
    assert client.get("/api/v1/categories/1.5", headers=headers).status_code == 422

    # text ID -> 422
    assert client.get("/api/v1/categories/abc", headers=headers).status_code == 422

    # valid positive but non-existing -> 404
    resp_404 = client.get("/api/v1/categories/999999", headers=headers)
    assert resp_404.status_code == 404


def test_get_category_by_id_cross_tenant(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    slug_b = f"catb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    cat_b = client.post(
        "/api/v1/categories",
        json={"name": "Tenant B Private Category"},
        headers=headers_b,
    ).json()

    # Tenant A attempts to get Tenant B's category -> 404
    resp_cross = client.get(f"/api/v1/categories/{cat_b['id']}", headers=headers_a)
    assert resp_cross.status_code == 404


# =====================================================================
# 4. PUT /api/v1/categories/{category_id}
# =====================================================================

def test_update_category_valid(tenant_fixture):
    headers = tenant_fixture["headers"]
    cat = client.post(
        "/api/v1/categories",
        json={"name": "Original Category", "description": "Original desc"},
        headers=headers,
    ).json()

    update_resp = client.put(
        f"/api/v1/categories/{cat['id']}",
        json={"name": "Updated Category", "description": "Updated description"},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["id"] == cat["id"]
    assert updated["name"] == "Updated Category"
    assert updated["description"] == "Updated description"


def test_update_category_validation(tenant_fixture):
    headers = tenant_fixture["headers"]
    cat = client.post(
        "/api/v1/categories",
        json={"name": "Base Category"},
        headers=headers,
    ).json()

    # Invalid category_id in path
    assert client.put("/api/v1/categories/0", json={"name": "New"}, headers=headers).status_code == 422
    assert client.put("/api/v1/categories/-1", json={"name": "New"}, headers=headers).status_code == 422
    assert client.put("/api/v1/categories/abc", json={"name": "New"}, headers=headers).status_code == 422

    # Invalid names in request body
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"name": ""}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"name": "   "}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"name": "string"}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"name": "1234"}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"name": "@#$%^"}, headers=headers).status_code == 422

    # Invalid descriptions in request body
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"description": ""}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"description": "   "}, headers=headers).status_code == 422
    assert client.put(f"/api/v1/categories/{cat['id']}", json={"description": "string"}, headers=headers).status_code == 422

    # Non-existing category_id -> 404
    assert client.put("/api/v1/categories/999999", json={"name": "Valid Name"}, headers=headers).status_code == 404


def test_update_category_parent_validation(tenant_fixture):
    headers = tenant_fixture["headers"]
    cat = client.post(
        "/api/v1/categories",
        json={"name": "Self Category"},
        headers=headers,
    ).json()

    # Self-parenting: parent_id == category_id -> 422
    resp_self = client.put(
        f"/api/v1/categories/{cat['id']}",
        json={"parent_id": cat["id"]},
        headers=headers,
    )
    assert resp_self.status_code == 422, f"Expected 422 for self-parenting, got {resp_self.status_code}"

    # Non-existing parent -> 404
    resp_nonexistent = client.put(
        f"/api/v1/categories/{cat['id']}",
        json={"parent_id": 999999},
        headers=headers,
    )
    assert resp_nonexistent.status_code == 404


def test_update_category_cross_tenant(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    slug_b = f"catb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    cat_b = client.post(
        "/api/v1/categories",
        json={"name": "Tenant B Cat"},
        headers=headers_b,
    ).json()

    # Tenant A attempts to update Tenant B's category -> 404
    resp_cross = client.put(
        f"/api/v1/categories/{cat_b['id']}",
        json={"name": "Hacked Category"},
        headers=headers_a,
    )
    assert resp_cross.status_code == 404


# =====================================================================
# 5. DELETE /api/v1/categories/{category_id}
# =====================================================================

def test_delete_category_valid(tenant_fixture):
    headers = tenant_fixture["headers"]
    cat = client.post(
        "/api/v1/categories",
        json={"name": "Category to Delete"},
        headers=headers,
    ).json()

    del_resp = client.delete(f"/api/v1/categories/{cat['id']}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    body = del_resp.json()
    assert body["success"] is True
    assert body["message"] == "Category deleted successfully"
    assert body["data"]["id"] == cat["id"]

    # Verify category is gone
    get_resp = client.get(f"/api/v1/categories/{cat['id']}", headers=headers)
    assert get_resp.status_code == 404


def test_delete_category_validation(tenant_fixture):
    headers = tenant_fixture["headers"]

    # ID 0 -> 422
    assert client.delete("/api/v1/categories/0", headers=headers).status_code == 422

    # Negative ID -> 422
    assert client.delete("/api/v1/categories/-1", headers=headers).status_code == 422

    # Text ID -> 422
    assert client.delete("/api/v1/categories/abc", headers=headers).status_code == 422

    # Non-existing ID -> 404
    assert client.delete("/api/v1/categories/999999", headers=headers).status_code == 404


def test_delete_category_cross_tenant(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    slug_b = f"catb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    cat_b = client.post(
        "/api/v1/categories",
        json={"name": "Tenant B Delete Target"},
        headers=headers_b,
    ).json()

    # Tenant A attempts to delete Tenant B's category -> 404
    resp_cross = client.delete(f"/api/v1/categories/{cat_b['id']}", headers=headers_a)
    assert resp_cross.status_code == 404


def test_delete_category_conflict_products(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    cat = client.post(
        "/api/v1/categories",
        json={"name": "Category With Products"},
        headers=headers,
    ).json()

    # Associate a product with this category via database
    db = SessionLocal()
    prod = Product(
        tenant_id=tenant_id,
        category_id=cat["id"],
        name="Associated Product",
        sku=f"SKU-{uuid.uuid4().hex[:6]}",
        price=Decimal("49.99"),
        cost_price=Decimal("30.00"),
    )
    db.add(prod)
    db.commit()
    db.close()

    # Deletion should be blocked with 409 Conflict
    del_resp = client.delete(f"/api/v1/categories/{cat['id']}", headers=headers)
    assert del_resp.status_code == 409, f"Expected 409 Conflict, got {del_resp.status_code}: {del_resp.text}"


def test_delete_category_conflict_subcategories(tenant_fixture):
    headers = tenant_fixture["headers"]

    parent_cat = client.post(
        "/api/v1/categories",
        json={"name": "Parent Category Conflict"},
        headers=headers,
    ).json()

    # Create child subcategory
    child_cat = client.post(
        "/api/v1/categories",
        json={"name": "Child Subcategory", "parent_id": parent_cat["id"]},
        headers=headers,
    ).json()

    # Deleting parent should be blocked with 409 Conflict
    del_resp = client.delete(f"/api/v1/categories/{parent_cat['id']}", headers=headers)
    assert del_resp.status_code == 409, f"Expected 409 Conflict, got {del_resp.status_code}: {del_resp.text}"
