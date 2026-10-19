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
        phone=f"9823{uuid.uuid4().hex[:6].upper()}",
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
        "user_id": user.id,
        "store_id": store.id,
        "warehouse_id": warehouse.id,
        "supplier_id": supplier.id,
        "product_id": product.id,
    }
    db.close()
    return data


@pytest.fixture
def tenant_a():
    return create_tenant_session("por-a")


@pytest.fixture
def tenant_b():
    return create_tenant_session("por-b")


# =====================================================================
# 1. Create Return, Auto-numbering & Item Enrichment
# =====================================================================

def test_create_purchase_order_return_and_enrichment(tenant_a):
    headers = tenant_a["headers"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    # 1. Create and receive PO
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 50, "unit_cost": 300.00}],
        },
        headers=headers,
    )
    assert po_resp.status_code == 201, po_resp.text
    po_data = po_resp.json()
    po_id = po_data["id"]
    po_item_id = po_data["items"][0]["id"]

    # Receive PO into inventory
    rec_resp = client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)
    assert rec_resp.status_code == 200, rec_resp.text

    # 2. Create Purchase Order Return for 10 units
    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Damaged goods packaging",
            "remarks": "Bags torn during transport",
            "items": [
                {
                    "purchase_order_item_id": po_item_id,
                    "quantity": 10,
                    "batch_number": "BATCH-001",
                    "item_reason": "Torn Bag",
                }
            ],
        },
        headers=headers,
    )
    assert ret_resp.status_code == 201, ret_resp.text
    ret_data = ret_resp.json()

    assert ret_data["status"] == "requested"
    assert ret_data["return_number"].startswith("POR-")
    assert ret_data["debit_note_number"].startswith("DN-")
    assert ret_data["supplier_id"] == supplier_id
    assert ret_data["supplier_name"] is not None
    assert float(ret_data["total_amount"]) == 3000.00
    assert len(ret_data["items"]) == 1
    assert ret_data["items"][0]["product_name"] is not None
    assert ret_data["items"][0]["product_sku"] is not None
    assert ret_data["items"][0]["batch_number"] == "BATCH-001"
    assert ret_data["items"][0]["item_reason"] == "Torn Bag"


# =====================================================================
# 2. Over-Return on Unreceived Goods Blocked & Partial PO Support
# =====================================================================

def test_over_return_on_unreceived_goods_blocked(tenant_a):
    headers = tenant_a["headers"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    # 1. Create PO for 100 units
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 100, "unit_cost": 250.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]

    # In draft state, creating return must fail with 409
    draft_ret = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Defective stock",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 10}],
        },
        headers=headers,
    )
    assert draft_ret.status_code == 409

    # 2. Receive partially via GRN (30 units received)
    grn_resp = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "items": [{"product_id": product_id, "ordered_quantity": 100, "received_quantity": 30}],
        },
        headers=headers,
    )
    grn_id = grn_resp.json()["id"]
    client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)

    # Verify PO status is partially_received
    po_check = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers).json()
    assert po_check["status"] == "partially_received"

    # 3. Attempting to return 50 units (more than 30 received) MUST be rejected with 409!
    over_ret = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Excess return attempt",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 50}],
        },
        headers=headers,
    )
    assert over_ret.status_code == 409, f"Expected 409, got {over_ret.status_code}: {over_ret.text}"
    assert "cannot exceed remaining returnable quantity" in over_ret.text

    # 4. Returning 10 units (<= 30 received) MUST succeed!
    valid_ret = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "10 Defective units found in partial delivery",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 10}],
        },
        headers=headers,
    )
    assert valid_ret.status_code == 201


# =====================================================================
# 3. Full Lifecycle: Approve -> Complete -> Stock Deduction
# =====================================================================

def test_return_lifecycle_approve_and_complete_deducts_inventory(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    # Create & receive PO for 40 units
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 40, "unit_cost": 200.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]
    client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)

    # Initial stock must be 40
    db = SessionLocal()
    inv_before = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv_before.quantity == Decimal("40.0000")
    db.close()

    # Create return for 15 units
    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Vendor recall",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 15}],
        },
        headers=headers,
    )
    ret_id = ret_resp.json()["id"]

    # 1. Approve return
    appr_resp = client.post(f"/api/v1/purchase-order-returns/{ret_id}/approve", headers=headers)
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "approved"
    assert appr_resp.json()["approved_at"] is not None

    # Stock is not deducted yet in approved state
    db = SessionLocal()
    inv_mid = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv_mid.quantity == Decimal("40.0000")
    db.close()

    # 2. Complete return
    comp_resp = client.post(f"/api/v1/purchase-order-returns/{ret_id}/complete", headers=headers)
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "completed"
    assert comp_resp.json()["completed_at"] is not None

    # 3. Verify stock is reduced by 15 (40 - 15 = 25)
    db = SessionLocal()
    inv_after = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv_after.quantity == Decimal("25.0000")

    # Verify StockMovement record
    movement = db.query(StockMovement).filter(
        StockMovement.tenant_id == tenant_id,
        StockMovement.store_id == store_id,
        StockMovement.product_id == product_id,
    ).order_by(StockMovement.id.desc()).first()
    assert movement is not None
    assert movement.quantity == 15
    assert "Vendor Return" in (movement.notes or "")
    db.close()


# =====================================================================
# 4. Status Patching Synchronization (No Stock-Out Bypass)
# =====================================================================

def test_status_patch_completed_deducts_inventory(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 20, "unit_cost": 150.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]
    client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)

    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Wrong model shipped",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 8}],
        },
        headers=headers,
    )
    ret_id = ret_resp.json()["id"]

    # First approve via PATCH status
    p1 = client.patch(f"/api/v1/purchase-order-returns/{ret_id}/status", json={"status": "approved"}, headers=headers)
    assert p1.status_code == 200
    assert p1.json()["status"] == "approved"

    # Then complete via PATCH status
    p2 = client.patch(f"/api/v1/purchase-order-returns/{ret_id}/status", json={"status": "completed"}, headers=headers)
    assert p2.status_code == 200
    assert p2.json()["status"] == "completed"

    # Verify inventory was deducted: 20 - 8 = 12
    db = SessionLocal()
    inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv.quantity == Decimal("12.0000")
    db.close()


# =====================================================================
# 5. Reject Return with Reason
# =====================================================================

def test_reject_purchase_order_return_with_reason(tenant_a):
    headers = tenant_a["headers"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 10, "unit_cost": 100.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]
    client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)

    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Customer cancellation",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 5}],
        },
        headers=headers,
    )
    ret_id = ret_resp.json()["id"]

    # Reject with explanation
    rej_resp = client.post(
        f"/api/v1/purchase-order-returns/{ret_id}/reject",
        json={"rejection_reason": "Vendor return window of 7 days expired"},
        headers=headers,
    )
    assert rej_resp.status_code == 200
    rej_data = rej_resp.json()
    assert rej_data["status"] == "rejected"
    assert rej_data["rejection_reason"] == "Vendor return window of 7 days expired"
    assert rej_data["rejected_at"] is not None

    # Cannot complete a rejected return
    c_resp = client.post(f"/api/v1/purchase-order-returns/{ret_id}/complete", headers=headers)
    assert c_resp.status_code == 409


# =====================================================================
# 6. Listing, Filters, Search & Dashboard Stats
# =====================================================================

def test_returns_dashboard_stats_and_by_number_and_export(tenant_a):
    headers = tenant_a["headers"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 25, "unit_cost": 200.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]
    client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)

    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Expired batch received",
            "debit_note_number": f"DN-CUSTOM-{uuid.uuid4().hex[:6].upper()}",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 10}],
        },
        headers=headers,
    )
    ret_data = ret_resp.json()
    ret_id = ret_data["id"]
    ret_number = ret_data["return_number"]
    dn_number = ret_data["debit_note_number"]

    # 1. Stats endpoint
    stats_resp = client.get("/api/v1/purchase-order-returns/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_returns"] >= 1
    assert float(stats["total_debit_amount"]) >= 2000.00
    assert len(stats["top_reasons"]) >= 1

    # 2. Direct by-number lookup
    by_num_resp = client.get(f"/api/v1/purchase-order-returns/by-number/{ret_number}", headers=headers)
    assert by_num_resp.status_code == 200
    assert by_num_resp.json()["id"] == ret_id

    # Lookup by debit note number
    by_dn_resp = client.get(f"/api/v1/purchase-order-returns/by-number/{dn_number}", headers=headers)
    assert by_dn_resp.status_code == 200
    assert by_dn_resp.json()["id"] == ret_id

    # 3. Export CSV via format=csv on /{return_id}/pdf
    csv_resp = client.get(f"/api/v1/purchase-order-returns/{ret_id}/pdf?format=csv", headers=headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert ret_number in csv_resp.text
    assert "DEBIT NOTE / VENDOR RETURN SLIP" in csv_resp.text


# =====================================================================
# 7. Debit Note / Return Slip PDF Generation
# =====================================================================

def test_purchase_order_return_pdf_export(tenant_a):
    headers = tenant_a["headers"]
    supplier_id = tenant_a["supplier_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 15, "unit_cost": 180.00}],
        },
        headers=headers,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]
    client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers)

    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Transit damage",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 5}],
        },
        headers=headers,
    )
    ret_id = ret_resp.json()["id"]

    # Preview mode
    pdf_prev = client.get(f"/api/v1/purchase-order-returns/{ret_id}/pdf?mode=preview", headers=headers)
    assert pdf_prev.status_code == 200
    assert pdf_prev.headers["content-type"] == "application/pdf"
    assert "inline" in pdf_prev.headers["content-disposition"]
    assert pdf_prev.content.startswith(b"%PDF-")

    # Download mode
    pdf_down = client.get(f"/api/v1/purchase-order-returns/{ret_id}/pdf?mode=download", headers=headers)
    assert pdf_down.status_code == 200
    assert pdf_down.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf_down.headers["content-disposition"]
    assert pdf_down.content.startswith(b"%PDF-")

    # Excel mode
    excel_down = client.get(f"/api/v1/purchase-order-returns/{ret_id}/pdf?format=excel", headers=headers)
    assert excel_down.status_code == 200
    assert "spreadsheetml" in excel_down.headers["content-type"]
    assert "attachment" in excel_down.headers["content-disposition"]
    assert len(excel_down.content) > 100


# =====================================================================
# 8. Cross-Tenant Security Isolation
# =====================================================================

def test_returns_cross_tenant_isolation(tenant_a, tenant_b):
    headers_a = tenant_a["headers"]
    headers_b = tenant_b["headers"]
    supplier_a = tenant_a["supplier_id"]
    store_a = tenant_a["store_id"]
    product_a = tenant_a["product_id"]

    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_a,
            "store_id": store_a,
            "items": [{"product_id": product_a, "quantity": 10, "unit_cost": 100.00}],
        },
        headers=headers_a,
    )
    po_id = po_resp.json()["id"]
    po_item_id = po_resp.json()["items"][0]["id"]
    client.post(f"/api/v1/purchase-orders/{po_id}/receive", json={}, headers=headers_a)

    ret_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={
            "purchase_order_id": po_id,
            "reason": "Confidential return",
            "items": [{"purchase_order_item_id": po_item_id, "quantity": 2}],
        },
        headers=headers_a,
    )
    ret_a_id = ret_resp.json()["id"]

    # Tenant B cannot view Tenant A's return
    get_b = client.get(f"/api/v1/purchase-order-returns/{ret_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # Tenant B cannot approve Tenant A's return
    appr_b = client.post(f"/api/v1/purchase-order-returns/{ret_a_id}/approve", headers=headers_b)
    assert appr_b.status_code == 404

    # Tenant B cannot complete Tenant A's return
    comp_b = client.post(f"/api/v1/purchase-order-returns/{ret_a_id}/complete", headers=headers_b)
    assert comp_b.status_code == 404

    # Tenant B cannot download Tenant A's PDF
    pdf_b = client.get(f"/api/v1/purchase-order-returns/{ret_a_id}/pdf", headers=headers_b)
    assert pdf_b.status_code == 404
