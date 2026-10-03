import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.category import Category
from app.models.product import Product
from app.models.supplier import Supplier

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"po-cat-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Admin",
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

    # Create a store
    store = Store(
        tenant_id=tenant_id,
        name=f"Store-{uuid.uuid4().hex[:4]}",
        address="123 Test St",
        is_active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    store_id = store.id

    # Create a supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name=f"Supplier-{uuid.uuid4().hex[:4]}",
        contact_person="John Doe",
        email=f"supp-{uuid.uuid4().hex[:6]}@example.com",
        phone="9876543210",
        address="Supplier address",
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    supplier_id = supplier.id

    # Create a product
    product = Product(
        tenant_id=tenant_id,
        name=f"Product-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        price=Decimal("150.00"),
        cost_price=Decimal("100.00"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    product_id = product.id

    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store_id,
        "supplier_id": supplier_id,
        "product_id": product_id,
    }


# =====================================================================
# 1. Categories - View API & Delete API Tests
# =====================================================================

def test_category_view_details_enriched(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    # 1. Create parent category
    parent_resp = client.post(
        "/api/v1/categories",
        json={"name": "Electronics Dept", "description": "All electronic devices"},
        headers=headers,
    )
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]

    # 2. Create child category with parent_id
    child_resp = client.post(
        "/api/v1/categories",
        json={
            "name": "Mobile Phones",
            "description": "Smartphones and tablets",
            "parent_id": parent_id,
        },
        headers=headers,
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    # 3. Associate a product with child category
    db = SessionLocal()
    prod = Product(
        tenant_id=tenant_id,
        category_id=child_id,
        name=f"Phone-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        price=Decimal("500.00"),
        cost_price=Decimal("350.00"),
    )
    db.add(prod)
    db.commit()
    db.close()

    # 4. GET /api/v1/categories/{child_id} -> should include parent_name, product_count, subcategory_count
    resp = client.get(f"/api/v1/categories/{child_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    cat_data = resp.json()
    assert cat_data["id"] == child_id
    assert cat_data["name"] == "Mobile Phones"
    assert cat_data["parent_id"] == parent_id
    assert cat_data["parent_name"] == "Electronics Dept"
    assert cat_data["product_count"] == 1
    assert cat_data["subcategory_count"] == 0
    assert "created_at" in cat_data

    # 5. GET /api/v1/categories/{parent_id} -> should have subcategory_count == 1
    p_resp = client.get(f"/api/v1/categories/{parent_id}", headers=headers)
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert p_data["parent_name"] is None
    assert p_data["subcategory_count"] == 1

    # 6. GET /api/v1/categories/{child_id}/details -> wrapped format
    details_resp = client.get(f"/api/v1/categories/{child_id}/details", headers=headers)
    assert details_resp.status_code == 200
    wrapped = details_resp.json()
    assert wrapped["success"] is True
    assert wrapped["message"] == "Category details retrieved successfully"
    assert wrapped["data"]["parent_name"] == "Electronics Dept"
    assert wrapped["data"]["product_count"] == 1


def test_category_delete_with_products_returns_clean_409(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    # Create category
    cat_resp = client.post(
        "/api/v1/categories",
        json={"name": "Kitchen Ware", "description": "Pots, pans, and cutlery"},
        headers=headers,
    )
    assert cat_resp.status_code == 201
    cat_id = cat_resp.json()["id"]

    # Attach product
    db = SessionLocal()
    prod = Product(
        tenant_id=tenant_id,
        category_id=cat_id,
        name=f"Frying Pan {uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        price=Decimal("25.00"),
        cost_price=Decimal("15.00"),
    )
    db.add(prod)
    db.commit()
    db.close()

    # Attempt delete -> MUST return 409 Conflict, NEVER 500 Internal Server Error
    del_resp = client.delete(f"/api/v1/categories/{cat_id}", headers=headers)
    assert del_resp.status_code == 409, f"Expected 409 Conflict, got {del_resp.status_code}: {del_resp.text}"
    body = del_resp.json()
    assert body["success"] is False
    assert "product" in body["message"].lower() or "associated" in body["message"].lower()


# =====================================================================
# 2. Purchase Orders - Invoice Column & Delete Functionality Tests
# =====================================================================

def test_purchase_order_create_with_invoice_number_and_list(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    product_id = tenant_fixture["product_id"]

    invoice_no = f"INV-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create Purchase Order with invoice_number
    create_payload = {
        "supplier_id": supplier_id,
        "store_id": store_id,
        "invoice_number": invoice_no,
        "notes": "Urgent order for weekend restocking",
        "items": [
            {
                "product_id": product_id,
                "quantity": 10,
                "unit_cost": 75.50,
            }
        ],
    }

    create_resp = client.post(
        "/api/v1/purchase-orders",
        json=create_payload,
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    po_data = create_resp.json()
    po_id = po_data["id"]
    assert po_data["invoice_number"] == invoice_no
    assert po_data["invoice_id"] == invoice_no
    assert po_data["store_id"] == store_id
    assert po_data["status"] == "draft"

    # 2. List Purchase Orders -> verify invoice_number appears in list items
    list_resp = client.get("/api/v1/purchase-orders", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    orders = list_resp.json()
    assert isinstance(orders, list)
    matching = [o for o in orders if o["id"] == po_id]
    assert len(matching) == 1
    assert matching[0]["invoice_number"] == invoice_no
    assert matching[0]["invoice_id"] == invoice_no

    # 3. GET /api/v1/purchase-orders/{id}
    single_resp = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers)
    assert single_resp.status_code == 200
    assert single_resp.json()["invoice_number"] == invoice_no

    # 4. PATCH /api/v1/purchase-orders/{id} -> update invoice_number
    updated_inv = f"INV-UPD-{uuid.uuid4().hex[:6].upper()}"
    patch_resp = client.patch(
        f"/api/v1/purchase-orders/{po_id}",
        json={"invoice_number": updated_inv},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["invoice_number"] == updated_inv
    assert patch_resp.json()["invoice_id"] == updated_inv


def test_purchase_order_delete_draft_order(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    product_id = tenant_fixture["product_id"]

    # 1. Create a draft PO
    create_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "invoice_number": "INV-DEL-TEST",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 5,
                    "unit_cost": 50.00,
                }
            ],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    po_id = create_resp.json()["id"]

    # 2. DELETE /api/v1/purchase-orders/{id}
    del_resp = client.delete(f"/api/v1/purchase-orders/{po_id}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    del_body = del_resp.json()
    assert del_body["success"] is True
    assert del_body["data"]["id"] == po_id

    # 3. Verify PO no longer exists
    get_resp = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers)
    assert get_resp.status_code == 404


def test_purchase_order_delete_received_order_blocked(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    product_id = tenant_fixture["product_id"]

    # 1. Create a PO
    create_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "invoice_number": "INV-REC-TEST",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 3,
                    "unit_cost": 40.00,
                }
            ],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    po_id = create_resp.json()["id"]

    # 2. Receive the PO (adds stock to inventory)
    rec_resp = client.post(
        f"/api/v1/purchase-orders/{po_id}/receive",
        json={"remarks": "Goods received in full"},
        headers=headers,
    )
    assert rec_resp.status_code == 200
    assert rec_resp.json()["status"] == "received"

    # 3. Attempting to DELETE received PO MUST return 409 Conflict
    del_resp = client.delete(f"/api/v1/purchase-orders/{po_id}", headers=headers)
    assert del_resp.status_code == 409, f"Expected 409 Conflict, got {del_resp.status_code}: {del_resp.text}"
    body = del_resp.json()
    assert body["success"] is False
    assert "received" in body["message"].lower() or "inventory" in body["message"].lower()

