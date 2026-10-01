import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"sup-{uuid.uuid4().hex[:8]}"
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
    db.close()

    return {"headers": headers, "tenant_id": tenant_id}


def test_supplier_purchase_history_validation(tenant_fixture):
    headers = tenant_fixture["headers"]

    # supplier_id = 0 -> 422 (Path gt=0)
    resp_zero = client.get("/api/v1/suppliers/0/purchase-history", headers=headers)
    assert resp_zero.status_code == 422

    # negative supplier_id -> 422 (Path gt=0)
    resp_neg = client.get("/api/v1/suppliers/-5/purchase-history", headers=headers)
    assert resp_neg.status_code == 422

    # non-integer supplier_id -> 422
    resp_str = client.get("/api/v1/suppliers/abc/purchase-history", headers=headers)
    assert resp_str.status_code == 422

    # valid but non-existing supplier_id -> 404
    resp_not_found = client.get("/api/v1/suppliers/999999/purchase-history", headers=headers)
    assert resp_not_found.status_code == 404


def test_supplier_zero_purchase_orders(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Create a new supplier with 0 purchase orders
    create_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Zero PO Supplier Alpha",
            "contact_person": "Contact Person",
            "email": f"zeropo-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543210",
            "address": "123 Street",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    supplier = create_resp.json()
    supplier_id = supplier["id"]

    # Request purchase history
    resp = client.get(f"/api/v1/suppliers/{supplier_id}/purchase-history", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["supplier_id"] == supplier_id
    assert data["supplier_name"] == supplier["name"]
    assert data["total_purchases"] == 0
    assert data["purchase_history"] == []
    assert data["message"] == "No purchase history found for this supplier"


def test_supplier_multiple_purchase_orders_and_items(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    # Create supplier
    create_sup = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Multi PO Supplier Beta",
            "contact_person": "Multi Person",
            "email": f"multipo-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543211",
            "address": "456 Avenue",
        },
        headers=headers,
    )
    assert create_sup.status_code == 201, create_sup.text
    supplier_id = create_sup.json()["id"]
    supplier_name = create_sup.json()["name"]

    # Create store and products via db for purchase order insertion
    db = SessionLocal()
    store = Store(tenant_id=tenant_id, name="Test Store", code=f"STR-{uuid.uuid4().hex[:6]}")
    db.add(store)
    prod1 = Product(tenant_id=tenant_id, name="Product 1", sku=f"SKU-{uuid.uuid4().hex[:6]}", price=Decimal("10.00"), cost_price=Decimal("8.00"))
    prod2 = Product(tenant_id=tenant_id, name="Product 2", sku=f"SKU-{uuid.uuid4().hex[:6]}", price=Decimal("20.00"), cost_price=Decimal("15.00"))
    db.add_all([prod1, prod2])
    db.commit()
    db.refresh(store)
    db.refresh(prod1)
    db.refresh(prod2)

    # Create 2 purchase orders, each with 2 items
    po1 = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        store_id=store.id,
        po_number=f"PO-{uuid.uuid4().hex[:8]}",
        status="received",
        total_amount=Decimal("100.00"),
        remarks="First PO with multiple items",
    )
    po2 = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        store_id=store.id,
        po_number=f"PO-{uuid.uuid4().hex[:8]}",
        status="draft",
        total_amount=Decimal("200.00"),
        remarks="Second PO with multiple items",
    )
    db.add_all([po1, po2])
    db.commit()
    db.refresh(po1)
    db.refresh(po2)

    item1_1 = PurchaseOrderItem(purchase_order_id=po1.id, product_id=prod1.id, quantity=5, unit_price=Decimal("10.00"), total=Decimal("50.00"))
    item1_2 = PurchaseOrderItem(purchase_order_id=po1.id, product_id=prod2.id, quantity=5, unit_price=Decimal("10.00"), total=Decimal("50.00"))
    item2_1 = PurchaseOrderItem(purchase_order_id=po2.id, product_id=prod1.id, quantity=10, unit_price=Decimal("10.00"), total=Decimal("100.00"))
    item2_2 = PurchaseOrderItem(purchase_order_id=po2.id, product_id=prod2.id, quantity=5, unit_price=Decimal("20.00"), total=Decimal("100.00"))
    db.add_all([item1_1, item1_2, item2_1, item2_2])
    db.commit()
    store_id = store.id
    prod1_id = prod1.id
    prod2_id = prod2.id
    db.close()

    # Call endpoint
    resp = client.get(f"/api/v1/suppliers/{supplier_id}/purchase-history", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["supplier_id"] == supplier_id
    assert data["supplier_name"] == supplier_name
    assert data["total_purchases"] == 2
    assert data["message"] == "Purchase history retrieved successfully"
    assert len(data["purchase_history"]) == 2

    # Verify nested schema structure
    for po in data["purchase_history"]:
        assert "id" in po
        assert po["tenant_id"] == tenant_id
        assert po["supplier_id"] == supplier_id
        assert po["store_id"] == store_id
        assert "po_number" in po
        assert po["status"] in ("draft", "received")
        assert Decimal(str(po["total_amount"])) > 0
        assert "created_at" in po
        assert "items" in po
        assert len(po["items"]) == 2
        for item in po["items"]:
            assert "id" in item
            assert item["product_id"] in (prod1_id, prod2_id)
            assert item["quantity"] > 0
            assert Decimal(str(item["unit_price"])) > 0
            assert Decimal(str(item["total"])) > 0


def test_supplier_cross_tenant_isolation(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    # Register tenant B
    slug_b = f"supb-{uuid.uuid4().hex[:8]}"
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
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant B creates a supplier
    create_sup_b = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Tenant B Supplier Gamma",
            "contact_person": "Person B",
            "email": f"supb-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543212",
            "address": "Tenant B Street",
        },
        headers=headers_b,
    )
    assert create_sup_b.status_code == 201
    supplier_b_id = create_sup_b.json()["id"]

    # Tenant A tries to access Tenant B's supplier purchase history -> 404
    resp_cross = client.get(f"/api/v1/suppliers/{supplier_b_id}/purchase-history", headers=headers_a)
    assert resp_cross.status_code == 404
