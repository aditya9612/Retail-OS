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
