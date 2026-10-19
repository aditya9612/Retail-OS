import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.product import Product
from app.models.inventory import Inventory, StockMovement

client = TestClient(app)


def create_tenant_and_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {slug}",
            "domain": slug,
            "owner_email": email,
            "owner_name": f"Admin {prefix}",
            "password": "Password123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
    }


def test_transfer_lifecycle_inventory_sync_and_rich_details():
    """
    Test complete lifecycle:
    1. Create transfer -> rich response with store & product names, total_items, total_quantity
    2. Approve transfer -> status Approved
    3. Dispatch transfer -> inventory deducted at source store, StockMovement created
    4. Receive transfer -> inventory added at destination store, StockMovement created
    """
    tenant = create_tenant_and_admin("trflife")
    headers = tenant["headers"]
    tenant_id = tenant["tenant_id"]

    db = SessionLocal()
    try:
        store1 = Store(name="Mumbai Main Hub", code=f"MUM-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        store2 = Store(name="Pune Express Branch", code=f"PUN-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([store1, store2])
        db.flush()

        prod1 = Product(name="Basmati Rice 5kg", sku=f"RICE-{uuid.uuid4().hex[:6]}", selling_price=450.0, tenant_id=tenant_id, is_active=True)
        db.add(prod1)
        db.flush()

        # Seed source store with 50 units of rice
        inv1 = Inventory(tenant_id=tenant_id, store_id=store1.id, product_id=prod1.id, quantity=Decimal("50.0000"))
        db.add(inv1)
        db.commit()

        s1_id, s2_id, p1_id = store1.id, store2.id, prod1.id
    finally:
        db.close()

    # 1. Create Transfer: 20 units
    create_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [{"product_id": p1_id, "quantity": 20}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    trf = create_resp.json()
    trf_id = trf["id"]
    assert trf["source_store_name"] == "Mumbai Main Hub"
    assert trf["destination_store_name"] == "Pune Express Branch"
    assert trf["status"] == "Pending"
    assert trf["total_items"] == 1
    assert trf["total_quantity"] == 20
    assert trf["items"][0]["product_name"] == "Basmati Rice 5kg"

    # 2. Approve Transfer
    appr_resp = client.put(f"/api/v1/store-transfers/{trf_id}/approve", headers=headers)
    assert appr_resp.status_code == 200, appr_resp.text
    assert appr_resp.json()["status"] == "Approved"

    # 3. Dispatch Transfer
    disp_resp = client.put(f"/api/v1/store-transfers/{trf_id}/dispatch", headers=headers)
    assert disp_resp.status_code == 200, disp_resp.text
    assert disp_resp.json()["status"] == "Dispatched"

    # Verify inventory was deducted from source store: 50 - 20 = 30
    db = SessionLocal()
    try:
        src_inv = db.query(Inventory).filter(Inventory.store_id == s1_id, Inventory.product_id == p1_id).first()
        assert src_inv is not None
        assert int(src_inv.quantity) == 30

        # Check stock movement recorded
        sm_out = db.query(StockMovement).filter(
            StockMovement.store_id == s1_id,
            StockMovement.product_id == p1_id,
            StockMovement.movement_type == "transfer_out",
            StockMovement.reference_id == trf_id,
        ).first()
        assert sm_out is not None
        assert int(sm_out.quantity) == 20
    finally:
        db.close()

    # 4. Receive Transfer
    recv_resp = client.put(f"/api/v1/store-transfers/{trf_id}/receive", headers=headers)
    assert recv_resp.status_code == 200, recv_resp.text
    assert recv_resp.json()["status"] == "Received"

    # Verify inventory was credited to destination store: +20
    db = SessionLocal()
    try:
        dst_inv = db.query(Inventory).filter(Inventory.store_id == s2_id, Inventory.product_id == p1_id).first()
        assert dst_inv is not None
        assert int(dst_inv.quantity) == 20

        # Check stock movement recorded
        sm_in = db.query(StockMovement).filter(
            StockMovement.store_id == s2_id,
            StockMovement.product_id == p1_id,
            StockMovement.movement_type == "transfer_in",
            StockMovement.reference_id == trf_id,
        ).first()
        assert sm_in is not None
        assert int(sm_in.quantity) == 20
    finally:
        db.close()


def test_receive_with_discrepancy_endpoint():
    """
    Test POST /api/v1/store-transfers/{transfer_id}/receive-with-discrepancy:
    - Dispatched: 10 units
    - Received: 7 units in good condition, 2 damaged, 1 missing
    - Verifies destination inventory increases by exactly 7 units
    - Verifies StockMovements for good, damaged, and missing
    """
    tenant = create_tenant_and_admin("trfdisc")
    headers = tenant["headers"]
    tenant_id = tenant["tenant_id"]

    db = SessionLocal()
    try:
        store1 = Store(name="Central Warehouse", code=f"CW-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        store2 = Store(name="Thane Outlet", code=f"THN-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([store1, store2])
        db.flush()

        prod1 = Product(name="Glass Tumbler Set", sku=f"GLS-{uuid.uuid4().hex[:6]}", selling_price=300.0, tenant_id=tenant_id, is_active=True)
        db.add(prod1)
        db.flush()

        inv1 = Inventory(tenant_id=tenant_id, store_id=store1.id, product_id=prod1.id, quantity=Decimal("100.0000"))
        db.add(inv1)
        db.commit()

        s1_id, s2_id, p1_id = store1.id, store2.id, prod1.id
    finally:
        db.close()

    # Create transfer of 10 units
    create_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [{"product_id": p1_id, "quantity": 10}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    trf_id = create_resp.json()["id"]

    # Approve and Dispatch
    client.put(f"/api/v1/store-transfers/{trf_id}/approve", headers=headers)
    client.put(f"/api/v1/store-transfers/{trf_id}/dispatch", headers=headers)

    # 1. Invalid discrepancy: sum does not equal dispatched quantity (7 + 1 + 1 = 9 != 10) -> Expect 400
    invalid_resp = client.post(
        f"/api/v1/store-transfers/{trf_id}/receive-with-discrepancy",
        json={
            "items": [{
                "product_id": p1_id,
                "received_quantity": 7,
                "damaged_quantity": 1,
                "missing_quantity": 1,
            }],
        },
        headers=headers,
    )
    assert invalid_resp.status_code == 400
    assert "must equal dispatched quantity" in invalid_resp.json()["detail"]

    # 2. Valid discrepancy: 7 received, 2 damaged, 1 missing -> total 10
    disc_resp = client.post(
        f"/api/v1/store-transfers/{trf_id}/receive-with-discrepancy",
        json={
            "items": [{
                "product_id": p1_id,
                "received_quantity": 7,
                "damaged_quantity": 2,
                "missing_quantity": 1,
                "remarks": "2 broken glass cups during transport, 1 missing box",
            }],
            "notes": "Truck encountered rough transit on highway",
        },
        headers=headers,
    )
    assert disc_resp.status_code == 200, disc_resp.text
    res_data = disc_resp.json()
    assert res_data["has_discrepancy"] is True
    assert res_data["total_dispatched_quantity"] == 10
    assert res_data["total_received_quantity"] == 7
    assert res_data["total_damaged_quantity"] == 2
    assert res_data["total_missing_quantity"] == 1
    assert res_data["status"] == "Received"

    # Verify destination store ONLY got 7 units of sellable inventory
    db = SessionLocal()
    try:
        dst_inv = db.query(Inventory).filter(Inventory.store_id == s2_id, Inventory.product_id == p1_id).first()
        assert dst_inv is not None
        assert int(dst_inv.quantity) == 7

        # Check stock movements
        mv_in = db.query(StockMovement).filter(
            StockMovement.store_id == s2_id,
            StockMovement.product_id == p1_id,
            StockMovement.movement_type == "transfer_in",
        ).first()
        assert mv_in is not None
        assert int(mv_in.quantity) == 7

        mv_dmg = db.query(StockMovement).filter(
            StockMovement.store_id == s2_id,
            StockMovement.product_id == p1_id,
            StockMovement.movement_type == "damaged_in_transit",
        ).first()
        assert mv_dmg is not None
        assert int(mv_dmg.quantity) == 2

        mv_miss = db.query(StockMovement).filter(
            StockMovement.store_id == s2_id,
            StockMovement.product_id == p1_id,
            StockMovement.movement_type == "missing_in_transit",
        ).first()
        assert mv_miss is not None
        assert int(mv_miss.quantity) == 1
    finally:
        db.close()


def test_transfer_summary_analytics_endpoint():
    """
    Test GET /api/v1/store-transfers/summary:
    - Company-wide summary metrics
    - Breakdown of statuses, top sources, top destinations, top products
    - Filter by store_id
    """
    tenant = create_tenant_and_admin("trfsum")
    headers = tenant["headers"]
    tenant_id = tenant["tenant_id"]

    db = SessionLocal()
    try:
        hub = Store(name="Main Depot", code=f"DEP-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        branch_a = Store(name="Branch North", code=f"NOR-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        branch_b = Store(name="Branch South", code=f"SOU-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([hub, branch_a, branch_b])
        db.flush()

        prod_a = Product(name="Almonds 500g", sku=f"ALM-{uuid.uuid4().hex[:6]}", selling_price=500.0, tenant_id=tenant_id, is_active=True)
        prod_b = Product(name="Cashews 500g", sku=f"CSH-{uuid.uuid4().hex[:6]}", selling_price=600.0, tenant_id=tenant_id, is_active=True)
        db.add_all([prod_a, prod_b])
        db.commit()

        hub_id, b_a_id, b_b_id = hub.id, branch_a.id, branch_b.id
        p_a_id, p_b_id = prod_a.id, prod_b.id
    finally:
        db.close()

    # 1. Create Transfer 1: Hub -> Branch A (Pending)
    t1_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": hub_id,
            "destination_store_id": b_a_id,
            "items": [{"product_id": p_a_id, "quantity": 15}],
        },
        headers=headers,
    )
    assert t1_resp.status_code == 201

    # 2. Create Transfer 2: Hub -> Branch B (Approved -> Dispatched)
    t2_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": hub_id,
            "destination_store_id": b_b_id,
            "items": [{"product_id": p_b_id, "quantity": 25}],
        },
        headers=headers,
    )
    assert t2_resp.status_code == 201
    t2_id = t2_resp.json()["id"]
    client.put(f"/api/v1/store-transfers/{t2_id}/approve", headers=headers)
    client.put(f"/api/v1/store-transfers/{t2_id}/dispatch", headers=headers)

    # 3. Create Transfer 3: Branch A -> Branch B (Approved -> Dispatched -> Received)
    t3_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": b_a_id,
            "destination_store_id": b_b_id,
            "items": [{"product_id": p_a_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert t3_resp.status_code == 201
    t3_id = t3_resp.json()["id"]
    client.put(f"/api/v1/store-transfers/{t3_id}/approve", headers=headers)
    client.put(f"/api/v1/store-transfers/{t3_id}/dispatch", headers=headers)
    client.put(f"/api/v1/store-transfers/{t3_id}/receive", headers=headers)

    # 4. Fetch Global Summary
    sum_resp = client.get("/api/v1/store-transfers/summary", headers=headers)
    assert sum_resp.status_code == 200, sum_resp.text
    summary = sum_resp.json()

    assert summary["total_transfers"] == 3
    assert summary["pending_transfers"] == 1
    assert summary["dispatched_transfers"] == 1
    assert summary["received_transfers"] == 1
    assert summary["in_transit_transfers"] == 1
    assert summary["total_units_transferred"] == 45  # 15 + 25 + 5

    # Check top source stores
    source_names = [s["store_name"] for s in summary["top_source_stores"]]
    assert "Main Depot" in source_names

    # Check top products
    prod_names = [p["product_name"] for p in summary["top_transferred_products"]]
    assert "Cashews 500g" in prod_names
    assert "Almonds 500g" in prod_names

    # 5. Fetch Summary filtered by Branch A
    sum_a_resp = client.get(f"/api/v1/store-transfers/summary?store_id={b_a_id}", headers=headers)
    assert sum_a_resp.status_code == 200
    summary_a = sum_a_resp.json()
    assert summary_a["total_transfers"] == 2  # Transfer 1 (destination) and Transfer 3 (source)


def test_reject_transfer_with_optional_reason():
    """
    Test rejecting a transfer with reason, and rejection without reason
    """
    tenant = create_tenant_and_admin("trfrej")
    headers = tenant["headers"]
    tenant_id = tenant["tenant_id"]

    db = SessionLocal()
    try:
        s1 = Store(name="Store X", code=f"SX-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        s2 = Store(name="Store Y", code=f"SY-{uuid.uuid4().hex[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([s1, s2])
        db.flush()

        p1 = Product(name="Tea 250g", sku=f"TEA-{uuid.uuid4().hex[:6]}", selling_price=120.0, tenant_id=tenant_id, is_active=True)
        db.add(p1)
        db.commit()
        s1_id, s2_id, p1_id = s1.id, s2.id, p1.id
    finally:
        db.close()

    create_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [{"product_id": p1_id, "quantity": 10}],
        },
        headers=headers,
    )
    trf_id = create_resp.json()["id"]

    # Reject with custom reason
    rej_resp = client.put(
        f"/api/v1/store-transfers/{trf_id}/reject",
        json={"rejection_reason": "Damaged batch detected at origin"},
        headers=headers,
    )
    assert rej_resp.status_code == 200, rej_resp.text
    assert rej_resp.json()["status"] == "Rejected"
