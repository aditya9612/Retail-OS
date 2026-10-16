import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.category import Category
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.store import Store
from app.models.store_transfer import StoreTransfer
from app.models.supplier import Supplier
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.store_transfer_service import StoreTransferService
from app.services.order_service import OrderService
from app.schemas.order import OrderCreate, OrderItemCreate
from app.utils.constants import OrderStatus

client = TestClient(app)


def test_full_enterprise_retail_lifecycle_end_to_end():
    """
    MASTER INTEGRATION TEST:
    Verifies complete end-to-end linking across the entire Retail-OS lifecycle:
    1. Tenant, Store, Warehouse, Supplier, and Product Setup
    2. Purchase Order creation
    3. Goods Receipt Note (GRN) auto inwarding & stock credit to Warehouse
    4. PO status synchronization (draft -> received)
    5. Internal Distribution (Warehouse -> Retail Store Transfer)
    6. POS Checkout & Realtime Store Stock Deduction
    7. Warehouse & Store Stock Integrity Verification
    """
    # -------------------------------------------------------------
    # Step 1: Tenant & Entities Setup
    # -------------------------------------------------------------
    slug = f"e2e-{uuid.uuid4().hex[:8]}"
    email = f"ceo-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Supermarket Chain {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Executive Admin",
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

    # Retail Store Outlet
    retail_store = Store(
        tenant_id=tenant_id,
        name="MG Road Superstore",
        code=f"MG-{uuid.uuid4().hex[:4].upper()}",
        address="100 MG Road, Pune",
        is_active=True,
        is_main=True,
    )
    db.add(retail_store)
    db.commit()
    db.refresh(retail_store)

    # Assign user to retail store for POS checkout
    user.store_id = retail_store.id
    db.commit()

    # Central Distribution Warehouse (with its own storage location)
    warehouse_store = Store(
        tenant_id=tenant_id,
        name="Central Hub Storage Location",
        code=f"HUB-LOC-{uuid.uuid4().hex[:4].upper()}",
        address="Plot 55 Chakan Logistics Park",
        is_active=True,
        is_main=False,
    )
    db.add(warehouse_store)
    db.commit()
    db.refresh(warehouse_store)

    warehouse = Warehouse(
        tenant_id=tenant_id,
        store_id=warehouse_store.id,
        name="Chakan Central Logistics Hub",
        code=f"WH-CHK-{uuid.uuid4().hex[:4].upper()}",
        address="Plot 55 Chakan Logistics Park",
        is_active=True,
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    # Supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name="Amul Dairy & Provisions Ltd",
        contact_person="Ramesh Patel",
        email=f"sales-{uuid.uuid4().hex[:6]}@amul.com",
        phone="9822114455",
        address="Anand, Gujarat",
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    # Product
    product = Product(
        tenant_id=tenant_id,
        name="Amul Pure Ghee 1L Tin",
        sku=f"GHEE-{uuid.uuid4().hex[:6].upper()}",
        price=Decimal("650.00"),
        cost_price=Decimal("520.00"),
        is_active=True,
    )
    db.add(product)
    db.commit()
    user_id = user.id
    product_id = product.id
    supplier_id = supplier.id
    wh_id = warehouse.id
    wh_store_id = warehouse_store.id
    retail_store_id = retail_store.id
    db.close()

    # -------------------------------------------------------------
    # Step 2: Procurement (Create Purchase Order for 100 units)
    # -------------------------------------------------------------
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": wh_store_id,  # PO ordered for central warehouse
            "invoice_number": f"PO-INV-{uuid.uuid4().hex[:6].upper()}",
            "notes": "Bulk festive stock procurement",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 100,
                    "unit_cost": 520.00,
                }
            ],
        },
        headers=headers,
    )
    assert po_resp.status_code == 201, po_resp.text
    po_data = po_resp.json()
    po_id = po_data["id"]
    assert po_data["status"] == "draft"
    assert float(po_data["total_amount"]) == 52000.00

    # -------------------------------------------------------------
    # Step 3: Inwarding (GRN received at Central Warehouse)
    # -------------------------------------------------------------
    grn_create_resp = client.post(
        "/api/v1/grn",
        json={
            "purchase_order_id": po_id,
            "warehouse_id": wh_id,
            "remarks": "Received in full via cold-chain container",
        },
        headers=headers,
    )
    assert grn_create_resp.status_code == 201, grn_create_resp.text
    grn_data = grn_create_resp.json()
    grn_id = grn_data["id"]
    assert grn_data["status"] == "pending"
    assert len(grn_data["items"]) == 1
    assert grn_data["items"][0]["received_quantity"] == 100

    # Receive the GRN -> triggers automated stock-in into Warehouse!
    rec_resp = client.post(f"/api/v1/grn/{grn_id}/receive", headers=headers)
    assert rec_resp.status_code == 200, rec_resp.text
    assert rec_resp.json()["status"] == "received"

    # Verify Warehouse stock is credited to exactly 100
    db = SessionLocal()
    wh_inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == wh_store_id,
        Inventory.product_id == product_id,
    ).first()
    assert wh_inv is not None
    assert wh_inv.quantity == Decimal("100.0000"), f"Expected 100 in WH, got {wh_inv.quantity}"

    # Verify PO status auto-synced to 'received'
    po_check = client.get(f"/api/v1/purchase-orders/{po_id}", headers=headers).json()
    assert po_check["status"] == "received"
    assert po_check["items"][0]["received_quantity"] == 100
    db.close()

    # -------------------------------------------------------------
    # Step 4: Internal Distribution (Warehouse -> Store Transfer 40 units)
    # -------------------------------------------------------------
    db = SessionLocal()
    # Create transfer
    transfer = StoreTransferService.create_transfer(
        db=db,
        source_store_id=wh_store_id,
        destination_store_id=retail_store_id,
        items=[{"product_id": product_id, "quantity": 40}],
        tenant_id=tenant_id,
    )
    transfer_id = transfer.id
    db.commit()

    # Approve transfer
    StoreTransferService.approve_transfer(
        db=db,
        transfer_id=transfer_id,
        approved_by=user_id,
        tenant_id=tenant_id,
    )
    db.commit()

    # Dispatch transfer from warehouse
    StoreTransferService.dispatch_transfer(
        db=db,
        transfer_id=transfer_id,
        tenant_id=tenant_id,
    )
    db.commit()

    # Receive transfer at retail store
    StoreTransferService.receive_transfer(
        db=db,
        transfer_id=transfer_id,
        tenant_id=tenant_id,
    )
    db.commit()

    # Verify Stock positions after transfer:
    # Warehouse should have: 100 - 40 = 60
    # Retail Store should have: 0 + 40 = 40
    wh_inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == wh_store_id,
        Inventory.product_id == product_id,
    ).first()
    assert wh_inv.quantity == Decimal("60.0000"), f"Expected 60 in warehouse, got {wh_inv.quantity}"

    store_inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == retail_store_id,
        Inventory.product_id == product_id,
    ).first()
    assert store_inv is not None
    assert store_inv.quantity == Decimal("40.0000"), f"Expected 40 in retail store, got {store_inv.quantity}"
    db.close()

    # -------------------------------------------------------------
    # Step 5: Retail POS Billing (Sell 5 units to customer)
    # -------------------------------------------------------------
    db = SessionLocal()
    order_svc = OrderService(db)
    pos_order = order_svc.create_order(
        tenant_id=tenant_id,
        user_id=user_id,
        data=OrderCreate(
            store_id=retail_store_id,
            order_type="pos",
            items=[
                OrderItemCreate(
                    product_id=product_id,
                    quantity=5,
                    unit_price=Decimal("650.00"),
                )
            ],
        ),
    )
    pos_order_id = pos_order.id
    db.commit()

    # Confirm order -> triggers automated stock deduction from Retail Store
    order_svc.confirm_order(tenant_id=tenant_id, order_id=pos_order_id)
    db.commit()

    # Verify Stock positions after sale:
    # Retail store inventory must reduce from 40 to 35!
    store_inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == retail_store_id,
        Inventory.product_id == product_id,
    ).first()
    assert store_inv.quantity == Decimal("35.0000"), f"Expected 35 in store after sale, got {store_inv.quantity}"

    # Warehouse inventory remains untouched at 60!
    wh_inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == wh_store_id,
        Inventory.product_id == product_id,
    ).first()
    assert wh_inv.quantity == Decimal("60.0000"), f"Expected 60 in WH, got {wh_inv.quantity}"
    db.close()

    # -------------------------------------------------------------
    # Step 6: Verify Live Warehouse Stock Endpoint
    # -------------------------------------------------------------
    wh_stock_resp = client.get(f"/api/v1/warehouses/{wh_id}/stock", headers=headers)
    assert wh_stock_resp.status_code == 200, wh_stock_resp.text
    wh_stock_data = wh_stock_resp.json()
    assert Decimal(str(wh_stock_data["total_quantity"])) == Decimal("60")
    assert len(wh_stock_data["data"]) == 1
    assert Decimal(str(wh_stock_data["data"][0]["quantity"])) == Decimal("60")
    assert wh_stock_data["data"][0]["product_id"] == product_id

    # -------------------------------------------------------------
    # Step 7: Verify Live Warehouse Transfers Endpoint
    # -------------------------------------------------------------
    wh_transfers_resp = client.get(f"/api/v1/warehouses/{wh_id}/transfers", headers=headers)
    assert wh_transfers_resp.status_code == 200, wh_transfers_resp.text
    wh_transfers_data = wh_transfers_resp.json()
    assert wh_transfers_data["total_transfers"] >= 1
    outbound = [t for t in wh_transfers_data["data"] if t["transfer_type"] == "outbound"]
    assert len(outbound) >= 1
    assert outbound[0]["destination_store_name"] == "MG Road Superstore"
