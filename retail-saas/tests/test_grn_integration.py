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


# =====================================================================
# 5. Direct Store Delivery (DSD), Logistics & Commercial Metadata
# =====================================================================

def test_direct_store_delivery_and_logistics_details(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    store_id = tenant_a["store_id"]
    product_id = tenant_a["product_id"]

    grn_payload = {
        "store_id": store_id,
        "invoice_number": "INV-MUM-8921",
        "invoice_date": "2026-10-18",
        "vehicle_number": "MH-12-AB-1234",
        "transporter_name": "VRL Logistics",
        "remarks": "Direct Store Delivery of organic rice",
        "items": [
            {
                "product_id": product_id,
                "ordered_quantity": 40,
                "received_quantity": 40,
                "unit_cost": 340.00,
                "remarks": "Passed seal check",
            }
        ],
    }

    resp = client.post("/api/v1/grn", json=grn_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    grn = resp.json()
    assert grn["store_id"] == store_id
    assert grn["store_name"] is not None
    assert grn["invoice_number"] == "INV-MUM-8921"
    assert grn["invoice_date"] == "2026-10-18"
    assert grn["vehicle_number"] == "MH-12-AB-1234"
    assert grn["transporter_name"] == "VRL Logistics"
    assert grn["total_items_count"] == 1
    assert grn["total_ordered_quantity"] == 40
    assert grn["total_received_quantity"] == 40
    assert Decimal(str(grn["total_cost_value"])) == Decimal("13600.00")
    grn_id = grn["id"]

    # Receive GRN into Store directly
    rec = client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)
    assert rec.status_code == 200, rec.text
    rec_data = rec.json()
    assert rec_data["status"] == "received"
    assert rec_data["received_at"] is not None

    # Verify inventory is credited to store_id
    db = SessionLocal()
    inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv is not None
    assert inv.quantity >= Decimal("40.0000")
    db.close()


# =====================================================================
# 6. Batch Number and Expiry Date Tracking
# =====================================================================

def test_grn_item_batch_and_expiry_date_tracking(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    warehouse_id = tenant_a["warehouse_id"]
    product_id = tenant_a["product_id"]

    batch_no = f"BAT-{uuid.uuid4().hex[:6].upper()}"
    expiry = "2027-12-31"

    grn_payload = {
        "warehouse_id": warehouse_id,
        "items": [
            {
                "product_id": product_id,
                "ordered_quantity": 15,
                "received_quantity": 15,
                "unit_cost": 300.00,
                "batch_number": batch_no,
                "expiry_date": expiry,
                "remarks": "FMCG stock with batch stamp",
            }
        ],
    }

    create_resp = client.post("/api/v1/grn", json=grn_payload, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    grn = create_resp.json()
    assert grn["items"][0]["batch_number"] == batch_no
    assert grn["items"][0]["expiry_date"] == expiry

    # Receive GRN
    rec_resp = client.post(f"/api/v1/grn/{grn['id']}/receive", headers=headers)
    assert rec_resp.status_code == 200, rec_resp.text

    # Verify ProductBatch record was created in database
    from app.models.product_batch import ProductBatch
    db = SessionLocal()
    batch_record = (
        db.query(ProductBatch)
        .filter(
            ProductBatch.tenant_id == tenant_id,
            ProductBatch.product_id == product_id,
            ProductBatch.batch_number == batch_no,
        )
        .first()
    )
    assert batch_record is not None, "ProductBatch must be persisted"
    assert str(batch_record.expiry_date) == expiry
    db.close()


# =====================================================================
# 7. Quality Check (QC Inspection) & Damaged Goods Handling
# =====================================================================

def test_grn_quality_inspection_qc(tenant_a):
    headers = tenant_a["headers"]
    tenant_id = tenant_a["tenant_id"]
    warehouse_id = tenant_a["warehouse_id"]
    product_id = tenant_a["product_id"]

    # Create GRN with 30 received units
    create_resp = client.post(
        "/api/v1/grn",
        json={
            "warehouse_id": warehouse_id,
            "items": [
                {
                    "product_id": product_id,
                    "ordered_quantity": 30,
                    "received_quantity": 30,
                    "unit_cost": 200.00,
                }
            ],
        },
        headers=headers,
    )
    grn = create_resp.json()
    grn_id = grn["id"]
    item_id = grn["items"][0]["id"]

    # Perform Quality Inspection: 26 accepted, 4 rejected (broken/damaged)
    qc_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 26,
                "rejected_quantity": 4,
                "damage_reason": "4 packs water-damaged during shipping",
                "remarks": "QC Inspector stamp verified",
            }
        ],
        "remarks": "Partial damage reported to vendor",
    }
    qc_resp = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=qc_payload, headers=headers)
    assert qc_resp.status_code == 200, qc_resp.text
    qc_data = qc_resp.json()
    assert qc_data["items"][0]["accepted_quantity"] == 26
    assert qc_data["items"][0]["rejected_quantity"] == 4
    assert qc_data["items"][0]["damage_reason"] == "4 packs water-damaged during shipping"
    assert qc_data["total_accepted_quantity"] == 26
    assert qc_data["total_rejected_quantity"] == 4

    # Receive GRN -> only 26 units should be credited into warehouse stock
    db = SessionLocal()
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    stock_before = Decimal("0.00")
    if wh.store_id:
        existing_inv = db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.store_id == wh.store_id,
            Inventory.product_id == product_id,
        ).first()
        if existing_inv:
            stock_before = existing_inv.quantity
    db.close()

    rec_resp = client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)
    assert rec_resp.status_code == 200

    db = SessionLocal()
    wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    inv_after = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == wh.store_id,
        Inventory.product_id == product_id,
    ).first()
    assert inv_after.quantity == stock_before + Decimal("26.0000"), "Only accepted quantity should be added to stock"
    db.close()


# =====================================================================
# 8. Enterprise Stats, Barcode Lookup, Export & HTML Slip
# =====================================================================

def test_grn_stats_and_by_number_lookup(tenant_a):
    headers = tenant_a["headers"]
    product_id = tenant_a["product_id"]

    # 1. Test Stats endpoint
    stats_resp = client.get("/api/v1/grn/stats", headers=headers)
    assert stats_resp.status_code == 200, stats_resp.text
    stats = stats_resp.json()
    assert "total_grns" in stats
    assert "pending_grns" in stats
    assert "received_grns" in stats
    assert "total_inward_value" in stats
    assert isinstance(stats["recent_grns"], list)

    # 2. Create GRN and lookup by number
    create_resp = client.post(
        "/api/v1/grn",
        json={
            "items": [{"product_id": product_id, "ordered_quantity": 5, "received_quantity": 5}],
        },
        headers=headers,
    )
    grn = create_resp.json()
    grn_number = grn["grn_number"]

    by_num_resp = client.get(f"/api/v1/grn/by-number/{grn_number}", headers=headers)
    assert by_num_resp.status_code == 200, by_num_resp.text
    assert by_num_resp.json()["id"] == grn["id"]

    # Non-existent number returns 404
    missing_resp = client.get("/api/v1/grn/by-number/GRN-DOES-NOT-EXIST", headers=headers)
    assert missing_resp.status_code == 404


def test_grn_export_and_print_slip(tenant_a):
    headers = tenant_a["headers"]
    product_id = tenant_a["product_id"]

    create_resp = client.post(
        "/api/v1/grn",
        json={
            "invoice_number": "INV-EXPORT-TEST",
            "items": [{"product_id": product_id, "ordered_quantity": 10, "received_quantity": 10}],
        },
        headers=headers,
    )
    grn_id = create_resp.json()["id"]

    # 1. Export CSV
    export_resp = client.get("/api/v1/grn/export", headers=headers)
    assert export_resp.status_code == 200, export_resp.text
    assert "text/csv" in export_resp.headers["content-type"]
    assert "GRN Number,Date,Status" in export_resp.text
    assert "INV-EXPORT-TEST" in export_resp.text

    # 2. Print HTML Slip
    slip_resp = client.get(f"/api/v1/grn/{grn_id}/print-slip", headers=headers)
    assert slip_resp.status_code == 200, slip_resp.text
    assert "text/html" in slip_resp.headers["content-type"]
    assert "<!DOCTYPE html>" in slip_resp.text
    assert "GOODS RECEIVED NOTE (GRN)" in slip_resp.text
    assert "QC Inspector Signature" in slip_resp.text
    assert "Print Slip" in slip_resp.text
    assert "Download PDF" in slip_resp.text

    # 3. Download PDF (Attachment)
    pdf_resp = client.get(f"/api/v1/grn/{grn_id}/download-pdf", headers=headers)
    assert pdf_resp.status_code == 200, pdf_resp.text
    assert "application/pdf" in pdf_resp.headers["content-type"]
    assert "attachment" in pdf_resp.headers["content-disposition"]
    assert len(pdf_resp.content) > 500
    assert pdf_resp.content[:4] == b"%PDF"

    # 4. Preview PDF (Inline)
    preview_resp = client.get(f"/api/v1/grn/{grn_id}/download-pdf?mode=preview", headers=headers)
    assert preview_resp.status_code == 200
    assert "application/pdf" in preview_resp.headers["content-type"]
    assert "inline" in preview_resp.headers["content-disposition"]
    assert preview_resp.content[:4] == b"%PDF"


def test_grn_reject_with_reason_and_history_timeline(tenant_a):
    headers = tenant_a["headers"]
    product_id = tenant_a["product_id"]

    create_resp = client.post(
        "/api/v1/grn",
        json={
            "remarks": "Wrong shipment delivery",
            "items": [{"product_id": product_id, "ordered_quantity": 8, "received_quantity": 8}],
        },
        headers=headers,
    )
    grn_id = create_resp.json()["id"]

    # Reject with custom reason
    reject_resp = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": "Wrong product specifications received from supplier"},
        headers=headers,
    )
    assert reject_resp.status_code == 200, reject_resp.text
    rej_data = reject_resp.json()
    assert rej_data["status"] == "rejected"
    assert rej_data["rejection_reason"] == "Wrong product specifications received from supplier"

    # Verify history timeline
    hist_resp = client.get(f"/api/v1/grn/{grn_id}/history", headers=headers)
    assert hist_resp.status_code == 200, hist_resp.text
    hist = hist_resp.json()
    assert hist["status"] == "rejected"
    assert len(hist["timeline"]) >= 2
    assert any(ev["event"] == "GRN Rejected" for ev in hist["timeline"])


def test_duplicate_invoice_and_duplicate_grn_prevention(tenant_a):
    headers = tenant_a["headers"]
    product_id = tenant_a["product_id"]
    warehouse_id = tenant_a["warehouse_id"]

    inv_num = f"INV-DUP-{uuid.uuid4().hex[:6].upper()}"

    # 1. First GRN with invoice creates successfully
    res1 = client.post(
        "/api/v1/grn",
        json={
            "warehouse_id": warehouse_id,
            "invoice_number": inv_num,
            "items": [{"product_id": product_id, "ordered_quantity": 10, "received_quantity": 10}],
        },
        headers=headers,
    )
    assert res1.status_code == 201

    # 2. Second GRN with same invoice number must return 409 Conflict
    res2 = client.post(
        "/api/v1/grn",
        json={
            "warehouse_id": warehouse_id,
            "invoice_number": inv_num,
            "items": [{"product_id": product_id, "ordered_quantity": 10, "received_quantity": 10}],
        },
        headers=headers,
    )
    assert res2.status_code == 409, f"Expected 409 duplicate invoice conflict, got: {res2.status_code}"
    assert "already exists" in res2.json()["message"].lower()

    # 3. Duplicate product in same item list must return 409 Conflict
    res3 = client.post(
        "/api/v1/grn",
        json={
            "warehouse_id": warehouse_id,
            "items": [
                {"product_id": product_id, "ordered_quantity": 5, "received_quantity": 5},
                {"product_id": product_id, "ordered_quantity": 3, "received_quantity": 3},
            ],
        },
        headers=headers,
    )
    assert res3.status_code == 409
    assert "duplicate product" in res3.json()["message"].lower()

