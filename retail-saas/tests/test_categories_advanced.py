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
def advanced_tenant_fixture():
    slug = f"catadv-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Category Adv Admin",
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
# 1. GET /api/v1/categories/tree
# =====================================================================

def test_category_tree_empty(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]
    resp = client.get("/api/v1/categories/tree", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "No categories found"
    assert body["data"] == []


def test_category_tree_hierarchy_and_product_count(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]
    tenant_id = advanced_tenant_fixture["tenant_id"]

    # 1. Create Root Category (Electronics)
    root_resp = client.post(
        "/api/v1/categories",
        json={"name": "Consumer Electronics", "description": "All home and personal tech"},
        headers=headers,
    )
    assert root_resp.status_code == 201
    root_id = root_resp.json()["id"]

    # 2. Create Subcategory (Smartphones)
    sub_resp = client.post(
        "/api/v1/categories",
        json={"name": "Smartphones", "description": "Mobile phones", "parent_id": root_id},
        headers=headers,
    )
    assert sub_resp.status_code == 201
    sub_id = sub_resp.json()["id"]

    # 3. Create Sub-subcategory (Cases & Covers)
    child_sub_resp = client.post(
        "/api/v1/categories",
        json={"name": "Cases and Covers", "description": "Protective phone cases", "parent_id": sub_id},
        headers=headers,
    )
    assert child_sub_resp.status_code == 201
    child_sub_id = child_sub_resp.json()["id"]

    # 4. Attach a product to Subcategory
    db = SessionLocal()
    prod = Product(
        tenant_id=tenant_id,
        category_id=sub_id,
        name="Pixel Smartphone",
        sku=f"SKU-{uuid.uuid4().hex[:6]}",
        selling_price=Decimal("699.00"),
        price=Decimal("699.00"),
        cost_price=Decimal("500.00"),
        is_active=True,
    )
    db.add(prod)
    db.commit()
    db.close()

    # 5. Fetch Tree
    tree_resp = client.get("/api/v1/categories/tree", headers=headers)
    assert tree_resp.status_code == 200
    tree_data = tree_resp.json()
    assert tree_data["success"] is True
    assert tree_data["message"] == "Category tree retrieved successfully"
    roots = tree_data["data"]
    assert len(roots) >= 1

    root_node = next((r for r in roots if r["id"] == root_id), None)
    assert root_node is not None
    assert root_node["name"] == "Consumer Electronics"
    assert len(root_node["children"]) == 1

    sub_node = root_node["children"][0]
    assert sub_node["id"] == sub_id
    assert sub_node["name"] == "Smartphones"
    assert sub_node["product_count"] == 1
    assert len(sub_node["children"]) == 1

    child_sub_node = sub_node["children"][0]
    assert child_sub_node["id"] == child_sub_id
    assert child_sub_node["name"] == "Cases and Covers"
    assert child_sub_node["product_count"] == 0


def test_category_tree_tenant_isolation(advanced_tenant_fixture):
    headers_a = advanced_tenant_fixture["headers"]

    # Tenant A creates category
    client.post(
        "/api/v1/categories",
        json={"name": "Tenant A Private Cat"},
        headers=headers_a,
    )

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

    # Tenant B tree should be empty
    tree_b = client.get("/api/v1/categories/tree", headers=headers_b).json()
    assert tree_b["data"] == []


# =====================================================================
# 2. GET /api/v1/categories/{category_id}/subcategories
# =====================================================================

def test_get_subcategories(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]

    # Create Parent
    parent_resp = client.post(
        "/api/v1/categories",
        json={"name": "Fashion and Apparel"},
        headers=headers,
    )
    parent_id = parent_resp.json()["id"]

    # Initial check - no subcategories
    sub_init = client.get(f"/api/v1/categories/{parent_id}/subcategories", headers=headers)
    assert sub_init.status_code == 200
    assert sub_init.json()["message"] == "No subcategories found"
    assert sub_init.json()["data"] == []

    # Create subcategories
    client.post("/api/v1/categories", json={"name": "Men Clothing", "parent_id": parent_id}, headers=headers)
    client.post("/api/v1/categories", json={"name": "Women Clothing", "parent_id": parent_id}, headers=headers)

    # Fetch subcategories
    sub_resp = client.get(f"/api/v1/categories/{parent_id}/subcategories", headers=headers)
    assert sub_resp.status_code == 200
    body = sub_resp.json()
    assert body["success"] is True
    assert body["message"] == "Subcategories retrieved successfully"
    assert len(body["data"]) == 2
    names = [s["name"] for s in body["data"]]
    assert "Men Clothing" in names
    assert "Women Clothing" in names
    assert all(s["parent_id"] == parent_id for s in body["data"])
    assert all(s["parent_name"] == "Fashion and Apparel" for s in body["data"])


def test_get_subcategories_nonexistent(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]
    resp = client.get("/api/v1/categories/999999/subcategories", headers=headers)
    assert resp.status_code == 404


# =====================================================================
# 3. GET /api/v1/categories/{category_id}/products
# =====================================================================

def test_get_category_products_pagination_and_filter(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]
    tenant_id = advanced_tenant_fixture["tenant_id"]

    # Create Category
    cat_resp = client.post("/api/v1/categories", json={"name": "Footwear Collection"}, headers=headers)
    cat_id = cat_resp.json()["id"]

    # Create 3 products
    db = SessionLocal()
    for i in range(1, 4):
        prod = Product(
            tenant_id=tenant_id,
            category_id=cat_id,
            name=f"Shoe Model {i}",
            sku=f"SHOE-{i}-{uuid.uuid4().hex[:4]}",
            selling_price=Decimal(f"{100 * i}.00"),
            price=Decimal(f"{100 * i}.00"),
            cost_price=Decimal(f"{50 * i}.00"),
            is_active=(i != 3),  # 1 and 2 are active, 3 is inactive
        )
        db.add(prod)
    db.commit()
    db.close()

    # 1. Fetch all products in category
    resp_all = client.get(f"/api/v1/categories/{cat_id}/products", headers=headers)
    assert resp_all.status_code == 200
    body_all = resp_all.json()
    assert body_all["success"] is True
    assert body_all["total"] == 3
    assert len(body_all["data"]) == 3
    assert body_all["category_id"] == cat_id
    assert body_all["category_name"] == "Footwear Collection"

    # 2. Filter active only
    resp_active = client.get(f"/api/v1/categories/{cat_id}/products?is_active=true", headers=headers)
    assert resp_active.status_code == 200
    assert resp_active.json()["total"] == 2

    # 3. Search filter
    resp_search = client.get(f"/api/v1/categories/{cat_id}/products?search=Model 1", headers=headers)
    assert resp_search.status_code == 200
    assert resp_search.json()["total"] == 1
    assert resp_search.json()["data"][0]["name"] == "Shoe Model 1"

    # 4. Pagination
    resp_page = client.get(f"/api/v1/categories/{cat_id}/products?page=1&page_size=2", headers=headers)
    assert resp_page.status_code == 200
    body_page = resp_page.json()
    assert body_page["total"] == 3
    assert len(body_page["data"]) == 2
    assert body_page["page"] == 1
    assert body_page["page_size"] == 2


def test_get_category_products_nonexistent(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]
    resp = client.get("/api/v1/categories/999999/products", headers=headers)
    assert resp.status_code == 404


# =====================================================================
# 4. PATCH /api/v1/categories/{category_id}/activate & /deactivate
# =====================================================================

def test_activate_and_deactivate_category(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]

    cat_resp = client.post(
        "/api/v1/categories",
        json={"name": "Winter Wear Specials"},
        headers=headers,
    )
    cat_id = cat_resp.json()["id"]
    assert cat_resp.json()["is_active"] is True

    # Deactivate
    deact_resp = client.patch(f"/api/v1/categories/{cat_id}/deactivate", headers=headers)
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False

    # Check via GET
    get_resp = client.get(f"/api/v1/categories/{cat_id}", headers=headers)
    assert get_resp.json()["is_active"] is False

    # Activate
    act_resp = client.patch(f"/api/v1/categories/{cat_id}/activate", headers=headers)
    assert act_resp.status_code == 200
    assert act_resp.json()["is_active"] is True


def test_activate_deactivate_nonexistent(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]
    assert client.patch("/api/v1/categories/999999/activate", headers=headers).status_code == 404
    assert client.patch("/api/v1/categories/999999/deactivate", headers=headers).status_code == 404


# =====================================================================
# 5. PATCH /api/v1/categories/{category_id} (Partial update)
# =====================================================================

def test_patch_category_partial(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]

    cat = client.post(
        "/api/v1/categories",
        json={"name": "Books & Stationery", "description": "Original text"},
        headers=headers,
    ).json()

    # Update only description via PATCH
    patch_resp = client.patch(
        f"/api/v1/categories/{cat['id']}",
        json={"description": "Updated book description only"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "Books & Stationery"
    assert data["description"] == "Updated book description only"


# =====================================================================
# 6. GET /api/v1/categories with Advanced Query Filters
# =====================================================================

def test_list_categories_query_filters(advanced_tenant_fixture):
    headers = advanced_tenant_fixture["headers"]

    # Create root category
    root = client.post("/api/v1/categories", json={"name": "Groceries Food"}, headers=headers).json()

    # Create child category
    child = client.post(
        "/api/v1/categories",
        json={"name": "Fresh Organic Veggies", "parent_id": root["id"]},
        headers=headers,
    ).json()

    # 1. Search filter
    search_resp = client.get("/api/v1/categories?search=Organic", headers=headers)
    assert search_resp.status_code == 200
    body = search_resp.json()
    assert any(c["id"] == child["id"] for c in body["data"])
    assert not any(c["id"] == root["id"] for c in body["data"])

    # 2. root_only filter
    root_resp = client.get("/api/v1/categories?root_only=true", headers=headers)
    assert root_resp.status_code == 200
    roots = root_resp.json()["data"]
    assert any(c["id"] == root["id"] for c in roots)
    assert not any(c["id"] == child["id"] for c in roots)

    # 3. parent_id filter
    parent_filter_resp = client.get(f"/api/v1/categories?parent_id={root['id']}", headers=headers)
    assert parent_filter_resp.status_code == 200
    children = parent_filter_resp.json()["data"]
    assert len(children) == 1
    assert children[0]["id"] == child["id"]

    # 4. Pagination
    page_resp = client.get("/api/v1/categories?page=1&page_size=1", headers=headers)
    assert page_resp.status_code == 200
    page_body = page_resp.json()
    assert page_body["total"] >= 2
    assert len(page_body["data"]) == 1
    assert page_body["page"] == 1
    assert page_body["page_size"] == 1

