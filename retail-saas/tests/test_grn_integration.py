import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.inventory import Inventory, StockMovement
from app.models.user import User

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
        name=f"Main-Store-{uuid.uuid4().hex[:4]}",
        address="123 Retail St",
        is_active=True,
        is_main=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)

    # Create Warehouse
    warehouse = Warehouse(
        tenant_id=tenant_id,
        name=f"Central-WH-{uuid.uuid4().hex[:4]}",
        code=f"WH-{uuid.uuid4().hex[:6].upper()}",
        address="Warehouse Plot 99",
        is_active=True,
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    # Create Supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name=f"Supplier-{uuid.uuid4().hex[:4]}",
        contact_person="Rajesh Kumar",
        email=f"sup-{uuid.uuid4().hex[:6]}@example.com",
        phone="9823000001",
        address="MIDC Industrial Area",
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    # Create Product
    product = Product(
        tenant_id=tenant_id,
        name=f"Basmati Rice 5kg-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        price=Decimal("450.00"),
        cost_price=Decimal("350.00"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    data = {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store.id,
        "warehouse_id": warehouse.id,
        "supplier_id": supplier.id,
        "product_id": product.id,
    }
    db.close()
    return data


@pytest.fixture
def tenant_a():
    return create_tenant_session("grn-a")


@pytest.fixture
def tenant_b():
    return create_tenant_session("grn-b")


# =====================================================================
# 1. Direct GRN to Warehouse & Auto Stock-In
# =====================================================================

def test_direct_grn_to_warehouse_and_auto_stock_in(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    warehouse_id = tenant_a["warehouse_id"]
    product_id = tenant_a["product_id"]

    # 1. Create GRN directed to warehouse
    grn_payload = {
        "warehouse_id": warehouse_id,
        "remarks": "Direct stock shipment from local farm",
        "items": [
            {
                "product_id": product_id,
                "ordered_quantity": 25,
                "received_quantity": 25,
                "unit_cost": 320.00,
                "remarks": "All bags in good condition",
            }
        ],
    }

    resp = client.post("/api/v1/grn", json=grn_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    grn_data = resp.json()
    assert grn_data["status"] == "pending"
    assert grn_data["warehouse_id"] == warehouse_id
    assert grn_data["warehouse_name"] is not None
    assert len(grn_data["items"]) == 1
    assert grn_data["items"][0]["received_quantity"] == 25
    assert grn_data["items"][0]["product_name"] is not None
    grn_id = grn_data["id"]

    # 2. Before receiving, verify no stock was added yet
    db = SessionLocal()
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if wh.store_id:
        inv = db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.store_id == wh.store_id,
            Inventory.product_id == product_id,
        ).first()
        qty = inv.quantity if inv else Decimal("0.00")
        assert qty == Decimal("0.00")
    db.close()

    # 3. Receive GRN
    rec_resp = client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)
    assert rec_resp.status_code == 200, rec_resp.text
    rec_data = rec_resp.json()
    assert rec_data["status"] == "received"
    assert rec_data["received_at"] is not None

    # 4. Verify stock is credited in warehouse inventory
    db = SessionLocal()
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    assert wh.store_id is not None, "Backing store must be created or linked for warehouse"
    inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == wh.store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv is not None, "Inventory record must be created"
    assert inv.quantity == Decimal("25.0000"), f"Expected 25, got {inv.quantity}"

    # Verify StockMovement record exists
    movement = db.query(StockMovement).filter(
        StockMovement.tenant_id == tenant_id,
        StockMovement.reference_id == grn_id,
        StockMovement.store_id == wh.store_id,
    ).first()
    assert movement is not None
    assert movement.movement_type in ("stock_in", "STOCK_IN")
    assert movement.quantity == 25
    assert movement.new_stock == Decimal("25.0000")
    db.close()


# =====================================================================
# 2. Purchase Order ➔ GRN Auto-Population & Status Linking
# =====================================================================

def test_purchase_order_grn_linking_and_status_sync(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    store_id = tenant_a["store_id"]
    supplier_id = tenant_a["supplier_id"]
    product_id = tenant_a["product_id"]

    # 1. Create a Purchase Order for 50 units
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "invoice_number": f"PO-INV-{uuid.uuid4().hex[:6].upper()}",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 50,
                    "unit_cost": 300.00,
                }
            ],
        },
        headers=headers,
    )
    assert po_resp.status_code == 201, po_resp.text
    po = po_resp.json()
    po_id = po["id"]
    assert po["status"] == "draft"

    # 2. Create GRN referencing PO without specifying items (should auto-populate 50 units)
    grn_create_resp = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "remarks": "First batch delivery against PO",
            "items": [
                {
                    "product_id": product_id,
                    "ordered_quantity": 50,
                    "received_quantity": 20,  # Partial delivery of 20 units
                    "remarks": "20 units received in good order",
                }
            ],
        },
        headers=headers,
    )
    assert grn_create_resp.status_code == 201, grn_create_resp.text
    grn_1 = grn_create_resp.json()
    assert grn_1["purchase_order_id"] == po_id
    assert grn_1["purchase_order_number"] == po["order_number"]
    assert grn_1["supplier_name"] is not None

    # 3. Receive GRN 1 (20 units)
    rec1_resp = client.post(f"/api/v1/grn/{grn_1['id']}/receive", headers=headers)
    assert rec1_resp.status_code == 200, rec1_resp.text

    # Verify PO status became 'partially_received'
    po_check1 = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers).json()
    assert po_check1["status"] == "partially_received"
    assert po_check1["items"][0]["received_quantity"] == 20

    # 4. Create second GRN for remaining 30 units (auto-populated)
    grn_create2_resp = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "remarks": "Final delivery for remaining units",
        },
        headers=headers,
    )
    assert grn_create2_resp.status_code == 201, grn_create2_resp.text
    grn_2 = grn_create2_resp.json()
    assert len(grn_2["items"]) == 1
    # Auto-populated remaining quantity must be 30
    assert grn_2["items"][0]["received_quantity"] == 30

    # 5. Receive GRN 2 (30 units)
    rec2_resp = client.post(f"/api/v1/grn/{grn_2['id']}/receive", headers=headers)
    assert rec2_resp.status_code == 200, rec2_resp.text

    # Verify PO status became 'received' (completed)
    po_check2 = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers).json()
    assert po_check2["status"] == "received"
    assert po_check2["items"][0]["received_quantity"] == 50

    # Verify Store inventory total is 50
    db = SessionLocal()
    inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv.quantity == Decimal("50.0000")
    db.close()


# =====================================================================
# 3. Idempotency & Conflict Prevention
# =====================================================================

def test_grn_double_receive_and_reject_conflicts(tenant_a):
    headers = tenant_a["headers"]
    product_id = tenant_a["product_id"]

    # Create GRN
    grn_resp = client.post(
        "/api/v1/grn",
        json={
            "remarks": "Conflict testing",
            "items": [{"product_id": product_id, "ordered_quantity": 5, "received_quantity": 5}],
        },
        headers=headers,
    )
    grn_id = grn_resp.json()["id"]

    # 1. Receive GRN
    r1 = client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)
    assert r1.status_code == 200

    # 2. Attempting to receive again must return 409 Conflict
    r2 = client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"

    # 3. Attempting to reject an already-received GRN must return 409 Conflict
    r3 = client.post(f"/api/v1/grn/{grn_id}/reject", headers=headers)
    assert r3.status_code == 409

    # 4. Attempting to delete an already-received GRN must return 409 Conflict
    r4 = client.delete(f"/api/v1/grn/{grn_id}", headers=headers)
    assert r4.status_code == 409


def test_grn_delete_pending_grn(tenant_a):
    headers = tenant_a["headers"]
    product_id = tenant_a["product_id"]

    # Create pending GRN
    grn_resp = client.post(
        "/api/v1/grn",
        json={
            "remarks": "GRN to be discarded",
            "items": [{"product_id": product_id, "ordered_quantity": 2, "received_quantity": 2}],
        },
        headers=headers,
    )
    grn_id = grn_resp.json()["id"]

    # Delete pending GRN
    del_resp = client.delete(f"/api/v1/grn/{grn_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Verify GET returns 404
    get_resp = client.get(f"/api/v1/grn/{grn_id}", headers=headers)
    assert get_resp.status_code == 404


# =====================================================================
# 4. Cross-Tenant Security Isolation
# =====================================================================

def test_grn_cross_tenant_isolation(tenant_a, tenant_b):
    headers_a = tenant_a["headers"]
    headers_b = tenant_b["headers"]
    product_a = tenant_a["product_id"]

    # Create GRN in Tenant A
    grn_resp = client.post(
        "/api/v1/grn",
        json={
            "remarks": "Tenant A Secret Shipment",
            "items": [{"product_id": product_a, "ordered_quantity": 10, "received_quantity": 10}],
        },
        headers=headers_a,
    )
    grn_a_id = grn_resp.json()["id"]

    # 1. Tenant B cannot view Tenant A's GRN
    get_b = client.get(f"/api/v1/grn/{grn_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # 2. Tenant B cannot receive Tenant A's GRN
    rec_b = client.post(f"/api/v1/grn/{grn_a_id}/receive", headers=headers_b)
    assert rec_b.status_code == 404

    # 3. Tenant B cannot delete Tenant A's GRN
    del_b = client.delete(f"/api/v1/grn/{grn_a_id}", headers=headers_b)
    assert del_b.status_code == 404

    # 4. Tenant B cannot create a GRN using Tenant A's warehouse
    spoofed = client.post(
        "/api/v1/grn",
        json={
            "warehouse_id": tenant_a["warehouse_id"],
            "items": [{"product_id": tenant_b["product_id"], "ordered_quantity": 5, "received_quantity": 5}],
        },
        headers=headers_b,
    )
    assert spoofed.status_code == 404
