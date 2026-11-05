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
from app.models.warehouse import Warehouse

client = TestClient(app)


@pytest.fixture
def grn_fixture():
    slug = f"grn-{uuid.uuid4().hex[:8]}"
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

    # Create warehouse
    warehouse = Warehouse(
        tenant_id=tenant_id,
        name=f"Main WH {slug}",
        code=f"WH-{uuid.uuid4().hex[:4].upper()}",
        address="123 Industrial Area Sector 5",
        is_active=True,
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    # Create supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name=f"Supplier-{uuid.uuid4().hex[:4]}",
        contact_person="Rajesh Kumar",
        email=f"supp-{uuid.uuid4().hex[:6]}@example.com",
        phone="9876543210",
        address="Supplier hub address",
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    # Create 2 products
    prod1 = Product(
        tenant_id=tenant_id,
        name=f"Product-In-PO-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        price=Decimal("200.00"),
        cost_price=Decimal("150.00"),
        is_active=True,
    )
    prod2 = Product(
        tenant_id=tenant_id,
        name=f"Product-Not-In-PO-{uuid.uuid4().hex[:4]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        price=Decimal("300.00"),
        cost_price=Decimal("220.00"),
        is_active=True,
    )
    db.add_all([prod1, prod2])
    db.commit()
    db.refresh(prod1)
    db.refresh(prod2)

    # Create a Purchase Order containing prod1
    po = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier.id,
        order_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
        status="issued",
        total_amount=Decimal("1500.00"),
    )
    db.add(po)
    db.commit()
    db.refresh(po)

    po_item = PurchaseOrderItem(
        po_id=po.id,
        product_id=prod1.id,
        quantity=10,
        unit_cost=Decimal("150.00"),
        total_cost=Decimal("1500.00"),
    )
    db.add(po_item)
    db.commit()

    po_id = po.id
    warehouse_id = warehouse.id
    prod1_id = prod1.id
    prod2_id = prod2.id

    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "warehouse_id": warehouse_id,
        "po_id": po_id,
        "prod1_id": prod1_id,
        "prod2_id": prod2_id,
    }


def test_grn_accepts_product_not_in_po_blocked(grn_fixture):
    """Bug 1: GRN Accepts a Product That Does Not Exist in the Purchase Order"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod2_id = grn_fixture["prod2_id"]  # Not in PO

    payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Received items check",
        "items": [
            {
                "product_id": prod2_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
                "remarks": "Batch 1 check",
            }
        ],
    }
    resp = client.post("/api/v1/grn", json=payload, headers=headers)
    assert resp.status_code == 400, resp.text
    err_text = resp.text.lower()
    assert "does not exist in purchase order" in err_text or "not exist in purchase order" in err_text


def test_grn_empty_and_junk_remarks_blocked(grn_fixture):
    """Bug 2: GRN API Accepts Empty Remarks / Junk Remarks"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # 1. Empty string remarks
    empty_remarks_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
                "remarks": "",
            }
        ],
    }
    resp = client.post("/api/v1/grn", json=empty_remarks_payload, headers=headers)
    assert resp.status_code == 422, resp.text
    assert "cannot be empty" in resp.text.lower()

    # 2. Junk remarks: purely numeric, repeating chars, special chars only
    junk_remarks = [
        "12345",
        "!#$$%%",
        "---",
        "ppppp",
        "++",
        "'''",
        "//",
        ">><<",
        "??",
        "\\\\",
        "||",
        "string",
    ]
    for junk in junk_remarks:
        payload = {
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "remarks": junk,
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                    "remarks": "Good condition",
                }
            ],
        }
        res = client.post("/api/v1/grn", json=payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for junk remark: {junk}, got {res.status_code}"


def test_grn_received_quantity_greater_than_ordered_blocked(grn_fixture):
    """Bug 3: GRN API Accepts Received Quantity Greater Than Ordered Quantity"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # Received > Ordered
    payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Over delivery attempt",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 10,
                "remarks": "Extra received",
            }
        ],
    }
    resp = client.post("/api/v1/grn", json=payload, headers=headers)
    assert resp.status_code == 422, resp.text
    assert "cannot be greater than ordered quantity" in resp.text.lower()

    # Zero ordered quantity
    zero_ordered_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Zero order test",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 0,
                "received_quantity": 0,
            }
        ],
    }
    resp2 = client.post("/api/v1/grn", json=zero_ordered_payload, headers=headers)
    assert resp2.status_code == 422, resp2.text


def test_grn_status_and_received_at_lifecycle(grn_fixture):
    """Bug 4 & 5: GRN Status Remains Pending After Goods Are Received & Received At Null"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # Case 1: Goods are received in payload
    payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Verified and received",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 8,
                "received_quantity": 8,
                "remarks": "Fully received",
            }
        ],
    }
    resp = client.post("/api/v1/grn", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "received"
    assert data["received_at"] is not None

    # Case 2: Goods not yet received (received_quantity = 0)
    payload_pending = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Order placed only",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 8,
                "received_quantity": 0,
            }
        ],
    }
    resp_pending = client.post("/api/v1/grn", json=payload_pending, headers=headers)
    assert resp_pending.status_code == 201, resp_pending.text
    data_pending = resp_pending.json()
    assert data_pending["status"] == "pending"
    assert data_pending["received_at"] is None


def test_grn_invalid_ids_and_empty_items(grn_fixture):
    """Test 0 IDs, empty items, and non-existent IDs"""
    headers = grn_fixture["headers"]
    prod1_id = grn_fixture["prod1_id"]

    # 1. purchase_order_id: 0
    resp1 = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": 0,
            "items": [{"product_id": prod1_id, "ordered_quantity": 5, "received_quantity": 5}],
        },
        headers=headers,
    )
    assert resp1.status_code == 422, resp1.text

    # 2. warehouse_id: 0
    resp2 = client.post(
        "/api/v1/grn",
        json={
            "warehouse_id": 0,
            "items": [{"product_id": prod1_id, "ordered_quantity": 5, "received_quantity": 5}],
        },
        headers=headers,
    )
    assert resp2.status_code == 422, resp2.text

    # 3. items: []
    resp3 = client.post(
        "/api/v1/grn",
        json={"items": []},
        headers=headers,
    )
    assert resp3.status_code == 422, resp3.text

    # 4. Non-existent PO id
    resp4 = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": 9999999,
            "items": [{"product_id": prod1_id, "ordered_quantity": 5, "received_quantity": 5}],
        },
        headers=headers,
    )
    assert resp4.status_code == 404, resp4.text


def test_grn_print_returns_printable_pdf(grn_fixture):
    """Bug fix: GRN Print API Returns JSON Instead of a Printable Document"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # 1. Create a GRN first
    payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Order received for printing test",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 10,
                "received_quantity": 10,
                "remarks": "Quality checked",
            }
        ],
    }
    create_resp = client.post("/api/v1/grn", json=payload, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    grn_id = create_resp.json()["id"]

    # 2. Call print API (default mode is download -> attachment)
    print_resp = client.get(f"/api/v1/grn/{grn_id}/print", headers=headers)
    assert print_resp.status_code == 200, print_resp.text
    # Verify Content-Type is PDF, NOT JSON!
    assert "application/pdf" in print_resp.headers.get("content-type", "")
    assert "application/json" not in print_resp.headers.get("content-type", "")

    # Default mode is download (attachment)
    assert "attachment" in print_resp.headers.get("content-disposition", "")
    assert ".pdf" in print_resp.headers.get("content-disposition", "")

    # Verify binary content starts with PDF magic header %PDF-
    assert print_resp.content.startswith(b"%PDF-")
    assert len(print_resp.content) > 500

    # 3. Test mode=preview (inline)
    preview_resp = client.get(f"/api/v1/grn/{grn_id}/print?mode=preview", headers=headers)
    assert preview_resp.status_code == 200
    assert "inline" in preview_resp.headers.get("content-disposition", "")
    assert preview_resp.content.startswith(b"%PDF-")


def test_grn_total_cost_value_nonzero_when_product_received(grn_fixture):
    """Bug fix: Total Cost Value Is Zero Despite Receiving a Product"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # Inward GRN with unit_cost=0 and accepted_quantity=0 (as sent by Swagger / UI defaults)
    payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Receiving goods verification",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
                "accepted_quantity": 0,
                "rejected_quantity": 0,
                "unit_cost": 0,
            }
        ],
    }
    resp = client.post("/api/v1/grn", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["total_received_quantity"] == 5
    assert data["total_accepted_quantity"] == 5
    assert Decimal(str(data["total_cost_value"])) > Decimal("0.00")
    assert Decimal(str(data["items"][0]["unit_cost"])) > Decimal("0.00")


def test_grn_generic_damage_reason_blocked(grn_fixture):
    """Bug fix: GRN Accepts a Generic Damage Reason"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    bad_damage_reasons = ["string", "damage", "test", "null", "undefined", "n/a", "12345", "----", "aaaa", "defect"]
    for bad in bad_damage_reasons:
        payload = {
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "remarks": "Inward check with damage",
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                    "accepted_quantity": 4,
                    "rejected_quantity": 1,
                    "damage_reason": bad,
                }
            ],
        }
        res = client.post("/api/v1/grn", json=payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad damage_reason '{bad}', got {res.status_code}: {res.text}"
        assert "damage reason" in res.text.lower()

    # Valid natural damage reason must succeed (201)
    good_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Inward check with damage",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
                "accepted_quantity": 4,
                "rejected_quantity": 1,
                "damage_reason": "Outer packaging carton torn during transit",
            }
        ],
    }
    good_res = client.post("/api/v1/grn", json=good_payload, headers=headers)
    assert good_res.status_code == 201, good_res.text
    assert (good_res.json()["items"][0].get("reason") or good_res.json()["items"][0].get("damage_reason")) == "Outer packaging carton torn during transit"


def test_grn_invalid_batch_number_blocked(grn_fixture):
    """Bug fix: GRN Accepts an Invalid Batch Number"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    bad_batch_numbers = ["string", "test", "null", "undefined", "n/a", "12345", "----", "aaaa", "temp", "batch"]
    for bad in bad_batch_numbers:
        payload = {
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "remarks": "Inward check with batch number",
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                    "batch_number": bad,
                }
            ],
        }
        res = client.post("/api/v1/grn", json=payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad batch_number '{bad}', got {res.status_code}: {res.text}"
        assert "batch number" in res.text.lower()

    # Valid natural batch number must succeed (201)
    good_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "Inward check with valid batch",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
                "batch_number": "LOT-2026-NOV-01",
            }
        ],
    }
    good_res = client.post("/api/v1/grn", json=good_payload, headers=headers)
    assert good_res.status_code == 201, good_res.text
    assert good_res.json()["items"][0]["batch_number"] == "LOT-2026-NOV-01"


def test_grn_invalid_vehicle_number_blocked(grn_fixture):
    """Bug fix: API accept vehicle number as a string"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    bad_vehicles = ["string", "test", "null", "undefined", "12345", "TRUCK", "----", "vehicle"]
    for bad in bad_vehicles:
        payload = {
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "vehicle_number": bad,
            "remarks": "Vehicle test receiving",
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                }
            ],
        }
        res = client.post("/api/v1/grn", json=payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad vehicle_number '{bad}', got {res.status_code}: {res.text}"
        assert "vehicle number" in res.text.lower()

    # Valid vehicle numbers must succeed (201)
    good_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "vehicle_number": "MH-12-AB-1234",
        "transporter_name": "VRL Logistics",
        "remarks": "Inward with valid logistics",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
            }
        ],
    }
    good_res = client.post("/api/v1/grn", json=good_payload, headers=headers)
    assert good_res.status_code == 201, good_res.text
    assert good_res.json()["vehicle_number"] == "MH-12-AB-1234"
    assert good_res.json()["transporter_name"] == "VRL Logistics"


def test_grn_invalid_transporter_name_blocked(grn_fixture):
    """Bug fix: API accept transporter name as a string"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    bad_transporters = ["string", "test", "null", "undefined", "dummy", "transporter", "12345", "aaaa"]
    for bad in bad_transporters:
        payload = {
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "transporter_name": bad,
            "remarks": "Transporter test receiving",
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                }
            ],
        }
        res = client.post("/api/v1/grn", json=payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad transporter_name '{bad}', got {res.status_code}: {res.text}"
        assert "transporter name" in res.text.lower()


def test_grn_stats_invalid_store_id_blocked_and_recent_grns_isolated(grn_fixture):
    """Bug fix: GRN Stats API Returns Data for a Different Store When an Invalid Store ID Is Provided"""
    headers = grn_fixture["headers"]
    tenant_id = grn_fixture["tenant_id"]

    db = SessionLocal()
    store = db.query(Store).filter(Store.tenant_id == tenant_id).first()
    if not store:
        store = Store(tenant_id=tenant_id, name="Test Store", code=f"ST-{uuid.uuid4().hex[:4]}", is_active=True)
        db.add(store)
        db.commit()
        db.refresh(store)
    store_id = store.id
    db.close()

    # 1. Invalid store_id must return 404
    bad_res = client.get("/api/v1/grn/stats?store_id=10000", headers=headers)
    assert bad_res.status_code == 404, f"Expected 404 for non-existent store_id, got {bad_res.status_code}: {bad_res.text}"
    assert "store not found" in bad_res.text.lower()

    # 2. Valid store_id returns 200 and recent_grns must only belong to that store
    good_res = client.get(f"/api/v1/grn/stats?store_id={store_id}", headers=headers)
    assert good_res.status_code == 200, good_res.text
    stats = good_res.json()
    assert "total_grns" in stats
    assert isinstance(stats["recent_grns"], list)
    for r in stats["recent_grns"]:
        assert r["store_id"] == store_id


def test_get_grn_by_number_strict_isolation_from_id(grn_fixture):
    """Bug fix: Get GRN and Get GRN by Number APIs Return the Same Information"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # Create a GRN
    payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "remarks": "GRN for number vs ID lookup test",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
                "accepted_quantity": 5,
            }
        ],
    }
    create_res = client.post("/api/v1/grn", json=payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    created = create_res.json()
    grn_id = created["id"]
    grn_number = created["grn_number"]

    # 1. Lookup by ID endpoint works
    res_by_id = client.get(f"/api/v1/grn/{grn_id}", headers=headers)
    assert res_by_id.status_code == 200
    assert res_by_id.json()["id"] == grn_id

    # 2. Duplicate /by-number endpoint removed, returns 404
    res_by_num = client.get(f"/api/v1/grn/by-number/{grn_number}", headers=headers)
    assert res_by_num.status_code == 404


def test_grn_qc_invalid_remarks_blocked(grn_fixture):
    """Bug fix: GRN Accepts an Invalid Remarks Value in Quality Check"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # Create GRN
    create_res = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "remarks": "GRN created for QC remarks validation test",
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                    "accepted_quantity": 5,
                }
            ],
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    grn = create_res.json()
    grn_id = grn["id"]
    item_id = grn["items"][0]["id"]

    # 1. Invalid remarks at root level (e.g. "string", "test", "dummy", "12345", etc.)
    bad_remarks = ["string", "test", "dummy", "sample", "null", "12345", "aaaa", ""]
    for bad in bad_remarks:
        qc_payload = {
            "items": [
                {
                    "item_id": item_id,
                    "accepted_quantity": 5,
                    "rejected_quantity": 0,
                }
            ],
            "remarks": bad,
        }
        res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=qc_payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad root remarks '{bad}', got {res.status_code}: {res.text}"
        assert "remarks" in res.text.lower()

    # 2. Invalid remarks at item level
    for bad in ["string", "test", "dummy", "12345"]:
        qc_payload = {
            "items": [
                {
                    "item_id": item_id,
                    "accepted_quantity": 5,
                    "rejected_quantity": 0,
                    "remarks": bad,
                }
            ],
            "remarks": "Valid inspection summary notes",
        }
        res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=qc_payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad item remarks '{bad}', got {res.status_code}: {res.text}"
        assert "remarks" in res.text.lower()

    # 3. Valid quality check request succeeds
    good_qc = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 4,
                "rejected_quantity": 1,
                "damage_reason": "Damaged bottle seal during unloading",
                "batch_number": "BATCH-2026-X9",
                "remarks": "Item passed physical inspection with one seal damaged",
            }
        ],
        "remarks": "Completed full quality inspection successfully",
    }
    good_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=good_qc, headers=headers)
    assert good_res.status_code == 200, good_res.text
    qc_data = good_res.json()
    assert "Completed full quality inspection successfully" in qc_data["remarks"]


def test_grn_qc_invalid_damage_reason_blocked(grn_fixture):
    """Bug fix: GRN Accepts an Invalid Damage Reason in Quality Check"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # Create GRN
    create_res = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "warehouse_id": grn_fixture["warehouse_id"],
            "remarks": "GRN for QC damage reason validation test",
            "items": [
                {
                    "product_id": prod1_id,
                    "ordered_quantity": 5,
                    "received_quantity": 5,
                    "accepted_quantity": 5,
                }
            ],
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    grn = create_res.json()
    grn_id = grn["id"]
    item_id = grn["items"][0]["id"]

    # 1. Generic placeholder damage reasons must be blocked (422)
    bad_damage_reasons = ["string", "test", "damage", "dummy", "sample", "null", "12345", "aaaa"]
    for bad in bad_damage_reasons:
        qc_payload = {
            "items": [
                {
                    "item_id": item_id,
                    "accepted_quantity": 4,
                    "rejected_quantity": 1,
                    "damage_reason": bad,
                }
            ],
            "remarks": "Valid QC notes",
        }
        res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=qc_payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad damage_reason '{bad}', got {res.status_code}: {res.text}"
        assert "damage reason" in res.text.lower()

    # 2. Missing damage reason when rejected_quantity > 0 must be blocked (422)
    missing_damage_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 4,
                "rejected_quantity": 1,
                "damage_reason": None,
            }
        ],
        "remarks": "Valid QC notes",
    }
    missing_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=missing_damage_payload, headers=headers)
    assert missing_res.status_code == 422, missing_res.text
    assert "damage reason is required" in missing_res.text.lower()

    # 3. Valid descriptive damage reason succeeds (200)
    good_qc = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 4,
                "rejected_quantity": 1,
                "damage_reason": "Carton torn and outer container cracked",
                "remarks": "Valid physical QC check notes",
            }
        ],
        "remarks": "Completed QC successfully with 1 rejected",
    }
    good_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=good_qc, headers=headers)
    assert good_res.status_code == 200, good_res.text
    qc_data = good_res.json()
    assert (qc_data["items"][0].get("reason") or qc_data["items"][0].get("damage_reason")) == "Carton torn and outer container cracked"



def test_grn_qc_expiry_date_equal_or_before_receiving_date_blocked(grn_fixture):
    """Bug fix: ADMIN---GRN---Quality check Grn---POST/api/v1/grn/{grn_id}/quality-check---GRN Accepts a Product Expiry Date Equal to the Receiving Date"""
    from datetime import date, timedelta
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # 1. Create a fresh pending GRN
    create_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "vehicle_number": "MH-12-QC-9999",
        "transporter_name": "Safe Transit Co",
        "remarks": "Pending GRN for Expiry Date QC check",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 10,
                "received_quantity": 10,
                "batch_number": "B-EXP-101",
            }
        ],
    }
    create_res = client.post("/api/v1/grn", json=create_payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    grn = create_res.json()
    grn_id = grn["id"]
    item_id = grn["items"][0]["id"]

    today_str = date.today().isoformat()
    past_str = (date.today() - timedelta(days=1)).isoformat()
    future_str = (date.today() + timedelta(days=180)).isoformat()

    # 2. Expiry date equal to receiving date (today) must be rejected with 422
    equal_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 10,
                "rejected_quantity": 0,
                "batch_number": "B-EXP-101",
                "expiry_date": today_str,
                "remarks": "QC checked",
            }
        ],
        "remarks": "QC with expiry equal to today",
    }
    equal_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=equal_payload, headers=headers)
    assert equal_res.status_code == 422, f"Expected 422 for expiry_date equal to receiving date, got {equal_res.status_code}: {equal_res.text}"
    assert "expiry date" in equal_res.text.lower()

    # 3. Expiry date in the past must also be rejected with 422
    past_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 10,
                "rejected_quantity": 0,
                "batch_number": "B-EXP-101",
                "expiry_date": past_str,
                "remarks": "QC checked",
            }
        ],
        "remarks": "QC with past expiry",
    }
    past_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=past_payload, headers=headers)
    assert past_res.status_code == 422, f"Expected 422 for past expiry_date, got {past_res.status_code}: {past_res.text}"
    assert "expiry date" in past_res.text.lower()

    # 4. Valid future expiry date must succeed (200)
    future_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 10,
                "rejected_quantity": 0,
                "batch_number": "B-EXP-101",
                "expiry_date": future_str,
                "remarks": "QC passed with valid future expiry",
            }
        ],
        "remarks": "QC passed",
    }
    future_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=future_payload, headers=headers)
    assert future_res.status_code == 200, future_res.text
    qc_data = future_res.json()
    assert qc_data["items"][0]["expiry_date"] == future_str



def test_grn_qc_invalid_batch_number_blocked(grn_fixture):
    """Bug fix: ADMIN---GRN---Quality check Grn---POST/api/v1/grn/{grn_id}/quality-check----GRN Accepts an Invalid Batch Number"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    create_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "vehicle_number": "MH-12-QC-1111",
        "transporter_name": "Rapid Logistics",
        "remarks": "Pending GRN for Batch Number QC test",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
            }
        ],
    }
    create_res = client.post("/api/v1/grn", json=create_payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    grn = create_res.json()
    grn_id = grn["id"]
    item_id = grn["items"][0]["id"]

    # 1. Invalid placeholder batch numbers must be blocked (422)
    bad_batches = ["string", "test", "dummy", "null", "12345", "aaaa", "batch"]
    for bad in bad_batches:
        qc_payload = {
            "items": [
                {
                    "item_id": item_id,
                    "accepted_quantity": 5,
                    "rejected_quantity": 0,
                    "batch_number": bad,
                    "remarks": "QC checked",
                }
            ],
            "remarks": "QC inspection",
        }
        res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=qc_payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for bad batch_number '{bad}', got {res.status_code}: {res.text}"
        assert "batch number" in res.text.lower()

    # 2. Valid batch number succeeds (200)
    good_qc = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 5,
                "rejected_quantity": 0,
                "batch_number": "BATCH-2026-QC01",
                "remarks": "QC passed with valid batch",
            }
        ],
        "remarks": "QC inspection passed",
    }
    good_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=good_qc, headers=headers)
    assert good_res.status_code == 200, good_res.text
    assert good_res.json()["items"][0]["batch_number"] == "BATCH-2026-QC01"


def test_grn_qc_received_quantity_without_acceptance_or_rejection_blocked(grn_fixture):
    """Bug fix: ADMIN---GRN---Quality check Grn---POST/api/v1/grn/{grn_id}/quality-check---GRN Allows Received Quantity Without Acceptance or Rejection"""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    create_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "vehicle_number": "MH-12-QC-2222",
        "transporter_name": "City Cargo",
        "remarks": "Pending GRN for quantity accounting test",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 5,
                "received_quantity": 5,
            }
        ],
    }
    create_res = client.post("/api/v1/grn", json=create_payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    grn = create_res.json()
    grn_id = grn["id"]
    item_id = grn["items"][0]["id"]

    # 1. accepted_quantity=0 and rejected_quantity=0 (neither accepted nor rejected) must be blocked (422)
    zero_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 0,
                "rejected_quantity": 0,
                "remarks": "Zero acceptance and zero rejection",
            }
        ],
        "remarks": "Zero acceptance check",
    }
    zero_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=zero_payload, headers=headers)
    assert zero_res.status_code == 422, f"Expected 422 for 0 accepted and 0 rejected, got {zero_res.status_code}: {zero_res.text}"
    assert "acceptance or rejection" in zero_res.text.lower() or "cannot be 0" in zero_res.text.lower()

    # 2. Partial disposition where accepted + rejected != received_quantity (3 != 5) must be blocked (400)
    mismatch_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 2,
                "rejected_quantity": 1,
                "damage_reason": "Damaged bottle seal during unloading",
                "remarks": "Partial check",
            }
        ],
        "remarks": "Partial check notes",
    }
    mismatch_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=mismatch_payload, headers=headers)
    assert mismatch_res.status_code == 400, f"Expected 400 for mismatch in inspected quantity, got {mismatch_res.status_code}: {mismatch_res.text}"
    assert "must equal received quantity" in mismatch_res.text.lower()

    # 3. Complete disposition where accepted + rejected == received_quantity (4 + 1 == 5) must succeed (200)
    complete_payload = {
        "items": [
            {
                "item_id": item_id,
                "accepted_quantity": 4,
                "rejected_quantity": 1,
                "damage_reason": "Damaged bottle seal during unloading",
                "remarks": "Full inspection completed",
            }
        ],
        "remarks": "Full QC completed successfully",
    }
    complete_res = client.post(f"/api/v1/grn/{grn_id}/quality-check", json=complete_payload, headers=headers)
    assert complete_res.status_code == 200, complete_res.text
    qc_data = complete_res.json()
    assert qc_data["items"][0]["accepted_quantity"] == 4
    assert qc_data["items"][0]["rejected_quantity"] == 1



def test_grn_reject_reason_and_damage_reason_consistency(grn_fixture):
    """Bug fix: ADMIN---GRN---Reject Grn---POST/api/v1/grn/{grn_id}/reject---The request uses the field reason, but the response returns the reason in damage reason instead of reason."""
    headers = grn_fixture["headers"]
    po_id = grn_fixture["po_id"]
    prod1_id = grn_fixture["prod1_id"]

    # 1. Create a fresh pending GRN
    create_payload = {
        "purchase_order_id": po_id,
        "warehouse_id": grn_fixture["warehouse_id"],
        "vehicle_number": "MH-12-REJ-1234",
        "transporter_name": "Speed Transport",
        "remarks": "Pending GRN to test rejection reason field alignment",
        "items": [
            {
                "product_id": prod1_id,
                "ordered_quantity": 10,
                "received_quantity": 10,
            }
        ],
    }
    create_res = client.post("/api/v1/grn", json=create_payload, headers=headers)
    assert create_res.status_code == 201, create_res.text
    grn_id = create_res.json()["id"]

    # 2. Rejection with invalid placeholder reason or empty reason must fail with 422
    for bad_r in ["string", "", "   "]:
        bad_res = client.post(f"/api/v1/grn/{grn_id}/reject", json={"reason": bad_r}, headers=headers)
        assert bad_res.status_code == 422, f"Expected 422 for bad reason '{bad_r}', got {bad_res.status_code}: {bad_res.text}"

    # 2b. Rejection via query parameter with invalid or valid reason
    query_bad = client.post(f"/api/v1/grn/{grn_id}/reject?reason=string", headers=headers)
    assert query_bad.status_code == 422

    # 3. Rejection with valid reason must return reason in BOTH root response and items
    expected_reason = "Shipment boxes completely waterlogged and damaged in transit"
    good_payload = {"reason": expected_reason}
    res = client.post(f"/api/v1/grn/{grn_id}/reject", json=good_payload, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["status"] == "rejected"
    # Root level fields: both reason and rejection_reason are returned
    assert data["reason"] == expected_reason

    # Items level fields: all quantities rejected, and reason and damage_reason match
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["received_quantity"] == 10
    assert item["accepted_quantity"] == 0
    assert item["rejected_quantity"] == 10
    assert item["reason"] == expected_reason


def test_grn_reject_strict_reason_validations(grn_fixture):
    headers = grn_fixture["headers"]
    grn_id = grn_fixture["grn_id"]

    # 1. Reject purely numeric reason (e.g. '12344')
    res_num = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": "12344"},
        headers=headers,
    )
    assert res_num.status_code == 422, res_num.text

    # 2. Reject special characters (e.g. '@#$$')
    res_spec = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": "@#$$"},
        headers=headers,
    )
    assert res_spec.status_code == 422, res_spec.text

    # 3. Reject repeating characters (e.g. 'ppppp')
    res_rep = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": "ppppp"},
        headers=headers,
    )
    assert res_rep.status_code == 422, res_rep.text

    # 4. Reject empty string / whitespace
    res_emp = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": "   "},
        headers=headers,
    )
    assert res_emp.status_code == 422, res_emp.text

    # 5. Reject placeholder string
    res_str = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": "string"},
        headers=headers,
    )
    assert res_str.status_code == 422, res_str.text

    # 6. Reject null
    res_null = client.post(
        f"/api/v1/grn/{grn_id}/reject",
        json={"reason": None},
        headers=headers,
    )
    assert res_null.status_code == 422, res_null.text
