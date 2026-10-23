from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.user import User
from app.models.warehouse import Warehouse

client = TestClient(app)


def create_tenant_session(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"user-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
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
    user = db.query(User).filter(User.email == email).first()
    tenant_id = user.tenant_id

    # Create Store
    store = Store(
        tenant_id=tenant_id,
        name=f"Store-{uuid.uuid4().hex[:4]}",
        address="Commercial Complex 404",
        is_active=True,
        is_main=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)

    # Create Warehouse
    warehouse = Warehouse(
        tenant_id=tenant_id,
        name=f"Warehouse-{uuid.uuid4().hex[:4]}",
        code=f"WH-{uuid.uuid4().hex[:6].upper()}",
        address="Logistics Park Sector 9",
        is_active=True,
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    # Create Supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name=f"Metro Suppliers {uuid.uuid4().hex[:4]}",
        contact_person="Ramesh Patel",
        email=f"metro-{uuid.uuid4().hex[:6]}@example.com",
        phone="9823112233",
        gstin="27ABCDE1234F1Z5",
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    # Create Products
    prod1 = Product(
        tenant_id=tenant_id,
        name=f"Flour 10kg-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-FLOUR-{uuid.uuid4().hex[:6].upper()}",
        price=Decimal("450.00"),
        cost_price=Decimal("350.00"),
        is_active=True,
    )
    prod2 = Product(
        tenant_id=tenant_id,
        name=f"Sugar 5kg-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-SUGAR-{uuid.uuid4().hex[:6].upper()}",
        price=Decimal("250.00"),
        cost_price=Decimal("180.00"),
        is_active=True,
    )
    db.add_all([prod1, prod2])
    db.commit()
    db.refresh(prod1)
    db.refresh(prod2)

    data = {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store.id,
        "warehouse_id": warehouse.id,
        "supplier_id": supplier.id,
        "product_1_id": prod1.id,
        "product_2_id": prod2.id,
    }
    db.close()
    return data


@pytest.fixture
def tenant_fixture():
    return create_tenant_session("po-ent")


def test_po_create_with_warehouse_taxes_and_discounts(tenant_fixture):
    headers = tenant_fixture["headers"]
    warehouse_id = tenant_fixture["warehouse_id"]
    supplier_id = tenant_fixture["supplier_id"]
    p1 = tenant_fixture["product_1_id"]
    p2 = tenant_fixture["product_2_id"]

    create_payload = {
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "invoice_number": f"INV-DC-{uuid.uuid4().hex[:6].upper()}",
        "notes": "Procurement for Central Warehouse",
        "discount_amount": 50.00,
        "shipping_charges": 100.00,
        "items": [
            {
                "product_id": p1,
                "quantity": 10,
                "unit_cost": 300.00,
                "tax_rate": 5.00,
                "hsn_code": "100630",
                "unit_of_measure": "bag",
            },
            {
                "product_id": p2,
                "quantity": 5,
                "unit_cost": 200.00,
                "tax_rate": 18.00,
                "hsn_code": "170199",
                "unit_of_measure": "bag",
            },
        ],
    }

    resp = client.post("/api/v1/purchase-orders", json=create_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    po = resp.json()

    assert po["status"] == "draft"
    assert po["warehouse_id"] == warehouse_id
    assert po["warehouse_name"] is not None
    assert po["supplier_name"] is not None
    assert po["created_by_name"] is not None

    # Line 1: 10 * 300 = 3000 + 5% (150) = 3150
    # Line 2: 5 * 200 = 1000 + 18% (180) = 1180
    # Subtotal = 4000
    # Total Tax = 330
    # Discount = 50, Shipping = 100
    # Total Amount = 4000 + 330 + 100 - 50 = 4380.00
    assert Decimal(str(po["subtotal"])) == Decimal("4000.00")
    assert Decimal(str(po["tax_amount"])) == Decimal("330.00")
    assert Decimal(str(po["total_amount"])) == Decimal("4380.00")
    assert po["total_quantity"] == 15
    assert po["remaining_quantity"] == 15
    assert po["total_received_quantity"] == 0


def test_po_list_with_search_filters_and_pagination_headers(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    p1 = tenant_fixture["product_1_id"]

    inv_code = f"SEARCH-{uuid.uuid4().hex[:6].upper()}"

    resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "invoice_number": inv_code,
            "items": [{"product_id": p1, "quantity": 8, "unit_cost": 120.00}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    po_id = resp.json()["id"]

    # 1. Search by invoice code
    search_resp = client.get(f"/api/v1/purchase-orders?search={inv_code}", headers=headers)
    assert search_resp.status_code == 200
    assert "X-Total-Count" in search_resp.headers
    results = search_resp.json()
    assert len(results) == 1
    assert results[0]["id"] == po_id

    # 2. Filter by status 'draft'
    status_resp = client.get("/api/v1/purchase-orders?status=draft", headers=headers)
    assert status_resp.status_code == 200
    assert all(o["status"] == "draft" for o in status_resp.json())

    # 3. Filter by non-existent status
    empty_resp = client.get("/api/v1/purchase-orders?status=cancelled", headers=headers)
    assert empty_resp.status_code == 200
    assert len(empty_resp.json()) == 0


def test_po_update_draft_items_and_rejection_of_non_draft_updates(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    p1 = tenant_fixture["product_1_id"]
    p2 = tenant_fixture["product_2_id"]

    resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": p1, "quantity": 10, "unit_cost": 100.00}],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    po = resp.json()
    po_id = po["id"]
    assert po["total_amount"] == "1000.00"

    # 1. Update items in draft PO
    update_resp = client.patch(
        f"/api/v1/purchase-orders/{po_id}",
        json={
            "notes": "Updated quantities after vendor confirmation",
            "items": [
                {"product_id": p1, "quantity": 5, "unit_cost": 100.00},
                {"product_id": p2, "quantity": 10, "unit_cost": 150.00},
            ],
        },
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert len(updated["items"]) == 2
    # 5 * 100 + 10 * 150 = 2000.00
    assert Decimal(str(updated["total_amount"])) == Decimal("2000.00")
    assert updated["total_quantity"] == 15

    # 2. Approve the PO
    app_resp = client.post(f"/api/v1/purchase-orders/{po_id}/approve", json={"notes": "Order approved"}, headers=headers)
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"
    assert app_resp.json()["approved_by_name"] is not None

    # 3. Attempting to update approved PO must return 409 Conflict (not misleading 404!)
    patch_blocked = client.patch(f"/api/v1/purchase-orders/{po_id}", json={"notes": "Should fail"}, headers=headers)
    assert patch_blocked.status_code == 409, f"Expected 409 Conflict, got {patch_blocked.status_code}: {patch_blocked.text}"


def test_po_approval_cancellation_and_delete_protection(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    p1 = tenant_fixture["product_1_id"]

    # 1. Create draft PO
    create_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": p1, "quantity": 10, "unit_cost": 50.00}],
        },
        headers=headers,
    )
    po_id = create_resp.json()["id"]

    # 2. Approve PO
    app_resp = client.post(f"/api/v1/purchase-orders/{po_id}/approve", json={"notes": "PO Approved by Manager"}, headers=headers)
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"

    # 3. Deleting approved PO must return 409 Conflict
    del_resp = client.delete(f"/api/v1/purchase-orders/{po_id}", headers=headers)
    assert del_resp.status_code == 409, f"Expected 409, got {del_resp.status_code}: {del_resp.text}"

    # 4. Cancel PO with reason
    cancel_resp = client.post(
        f"/api/v1/purchase-orders/{po_id}/cancel",
        json={"reason": "Supplier out of raw materials for next 3 months"},
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    cancelled = cancel_resp.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancellation_reason"] == "Supplier out of raw materials for next 3 months"

    # 5. Cancelled PO cannot be received
    rec_blocked = client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)
    assert rec_blocked.status_code == 409


def test_po_partial_receiving_and_no_stock_duplication(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    p1 = tenant_fixture["product_1_id"]

    # 1. Create PO for 40 units
    create_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": p1, "quantity": 40, "unit_cost": 250.00}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    po_id = create_resp.json()["id"]

    # 2. Partial receive: 15 units
    rec1_resp = client.post(
        f"/api/v1/purchase-orders/{po_id}/receive",
        json={
            "remarks": "First delivery: 15 units",
            "items": [{"product_id": p1, "quantity": 15}],
        },
        headers=headers,
    )
    assert rec1_resp.status_code == 200, rec1_resp.text
    po1 = rec1_resp.json()
    assert po1["status"] == "partially_received"
    assert po1["total_received_quantity"] == 15
    assert po1["remaining_quantity"] == 25

    # Check store inventory is exactly 15
    db = SessionLocal()
    inv1 = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == p1,
    ).first()
    assert inv1 is not None
    assert inv1.quantity == Decimal("15.0000")
    db.close()

    # 3. Receive remaining units (without specifying item list -> should inward remaining 25, NOT all 40!)
    rec2_resp = client.post(
        f"/api/v1/purchase-orders/{po_id}/receive",
        json={"remarks": "Second and final delivery for remaining balance"},
        headers=headers,
    )
    assert rec2_resp.status_code == 200, rec2_resp.text
    po2 = rec2_resp.json()
    assert po2["status"] == "received"
    assert po2["total_received_quantity"] == 40
    assert po2["remaining_quantity"] == 0

    # Verify inventory is exactly 40 (preventing the critical 15 + 40 = 55 duplicate bug!)
    db = SessionLocal()
    inv2 = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == p1,
    ).first()
    assert inv2.quantity == Decimal("40.0000"), f"Expected 40, got {inv2.quantity}"
    db.close()

    # 4. State Machine Validation: Attempting to revert received PO to draft or cancelled must fail with 409
    revert_resp = client.patch(
        f"/api/v1/purchase-orders/{po_id}/status",
        json={"status": "draft"},
        headers=headers,
    )
    assert revert_resp.status_code == 409, f"Expected 409, got {revert_resp.status_code}: {revert_resp.text}"


def test_po_stats(tenant_fixture):
    headers = tenant_fixture["headers"]
    supplier_id = tenant_fixture["supplier_id"]
    store_id = tenant_fixture["store_id"]
    p1 = tenant_fixture["product_1_id"]

    # Create a PO to ensure data exists
    client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": p1, "quantity": 10, "unit_cost": 100.00}],
        },
        headers=headers,
    )

    # 1. Stats endpoint works
    stats_resp = client.get("/api/v1/purchase-orders/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_orders" in stats
    assert "draft_orders" in stats
    assert "total_order_value" in stats
    assert stats["total_orders"] >= 1

    # 2. Verify /dashboard and /export are removed
    routes = [getattr(r, "path", "") for r in app.routes]
    assert "/api/v1/purchase-orders/dashboard" not in routes
    assert "/api/v1/purchase-orders/export" not in routes


def test_po_get_linked_grns(tenant_fixture):
    headers = tenant_fixture["headers"]
    store_id = tenant_fixture["store_id"]
    supplier_id = tenant_fixture["supplier_id"]
    p1 = tenant_fixture["product_1_id"]

    # 1. Create PO
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": p1, "quantity": 20, "unit_cost": 100.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]

    # 2. Create GRN against PO
    grn_resp = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "remarks": "Receiving against PO",
        },
        headers=headers,
    )
    assert grn_resp.status_code == 201

    # 3. GET /api/v1/purchase-orders/{id}/grns
    linked_resp = client.get(f"/api/v1/purchase-orders/{po_id}/grns", headers=headers)
    assert linked_resp.status_code == 200
    grns = linked_resp.json()
    assert len(grns) == 1
    assert grns[0]["purchase_order_id"] == po_id

