import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.store import Store
from app.models.store_transfer import StoreTransfer

client = TestClient(app)


def _register_and_login(slug_prefix: str = "sttest"):
    suffix = uuid.uuid4().hex[:6]
    owner_email = f"owner_{slug_prefix}_{suffix}@testmart.com"
    owner_pass = "Password@123!"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Main {slug_prefix} {suffix}",
            "domain": f"{slug_prefix}-{suffix}",
            "owner_email": owner_email,
            "owner_name": f"Owner {slug_prefix}",
            "password": owner_pass,
            "plan_code": "enterprise",
        },
    )
    assert reg_res.status_code == 200, f"Register failed: {reg_res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": owner_pass},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = reg_res.json()["tenant_id"]

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "suffix": suffix,
    }


def _create_test_store(headers, name: str, is_warehouse: bool, is_main: bool = False):
    suffix = uuid.uuid4().hex[:4].upper()
    res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={
            "name": name,
            "code": f"STR-{suffix}",
            "address": "123 Test Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "phone": "9876543210",
            "email": f"store_{suffix.lower()}@test.com",
            "is_main": is_main,
            "is_active": True,
            "is_warehouse": is_warehouse,
        },
    )
    assert res.status_code == 201, f"Failed to create store: {res.text}"
    return res.json()


# =========================================================================
# 1. Tests for Create Store API - is_warehouse Field
# =========================================================================

def test_create_store_is_warehouse_false():
    """Verify that creating a store with is_warehouse: false returns and saves false."""
    ctx = _register_and_login("whfalse")
    headers = ctx["headers"]

    payload = {
        "name": "Masala Retail Store",
        "code": f"STR-{uuid.uuid4().hex[:4].upper()}",
        "address": "MUMBAI",
        "city": "MUMBAI",
        "state": "Maharashtra",
        "pincode": "854123",
        "phone": "8541203256",
        "email": "masala_store@gmail.com",
        "is_main": False,
        "is_active": True,
        "is_warehouse": False,
    }

    res = client.post("/api/v1/stores/", headers=headers, json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    # 1. API Response has is_warehouse: false
    assert data["is_warehouse"] is False
    assert data["is_main"] is False
    store_id = data["id"]

    # 2. GET by ID returns is_warehouse: false
    get_res = client.get(f"/api/v1/stores/{store_id}", headers=headers)
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["is_warehouse"] is False

    # 3. Database persistence check
    db: Session = SessionLocal()
    try:
        db_store = db.query(Store).filter(Store.id == store_id).first()
        assert db_store is not None
        assert db_store.is_warehouse is False
        assert db_store.is_main is False
    finally:
        db.close()


def test_create_store_is_warehouse_true():
    """Verify that creating a store with is_warehouse: true returns and saves true."""
    ctx = _register_and_login("whtrue")
    headers = ctx["headers"]

    payload = {
        "name": "Central Depot Warehouse",
        "code": f"WH-{uuid.uuid4().hex[:4].upper()}",
        "address": "Hadapsar Industrial Estate, Pune",
        "city": "PUNE",
        "state": "Maharashtra",
        "pincode": "411028",
        "phone": "8541203257",
        "email": "central_wh@gmail.com",
        "is_main": False,
        "is_active": True,
        "is_warehouse": True,
    }

    res = client.post("/api/v1/stores/", headers=headers, json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    # 1. API Response has is_warehouse: true
    assert data["is_warehouse"] is True
    assert data["is_main"] is False
    store_id = data["id"]

    # 2. GET by ID returns is_warehouse: true
    get_res = client.get(f"/api/v1/stores/{store_id}", headers=headers)
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["is_warehouse"] is True

    # 3. Database persistence check
    db: Session = SessionLocal()
    try:
        db_store = db.query(Store).filter(Store.id == store_id).first()
        assert db_store is not None
        assert db_store.is_warehouse is True
        assert db_store.is_main is False
    finally:
        db.close()


def test_patch_store_is_warehouse():
    """Verify updating is_warehouse via PATCH works for both directions."""
    ctx = _register_and_login("whpatch")
    headers = ctx["headers"]

    store = _create_test_store(headers, "Switch Store Branch", is_warehouse=False)
    store_id = store["id"]
    assert store["is_warehouse"] is False

    # Switch False -> True
    p1 = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"is_warehouse": True})
    assert p1.status_code == 200, p1.text
    assert p1.json()["is_warehouse"] is True

    # Switch True -> False
    p2 = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"is_warehouse": False})
    assert p2.status_code == 200, p2.text
    assert p2.json()["is_warehouse"] is False


# =========================================================================
# 2. Tests for Store Transfer - Reject Transfer API & rejection_reason
# =========================================================================

def test_reject_store_transfer_with_reason():
    """Verify rejecting transfer saves and returns rejection_reason in response and get."""
    ctx = _register_and_login("trfreject")
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]

    # Create 2 stores
    s1 = _create_test_store(headers, "Source Outlet Store", is_warehouse=False)
    s2 = _create_test_store(headers, "Destination Outlet Store", is_warehouse=False)

    # Create a product and inventory
    db: Session = SessionLocal()
    try:
        prod = Product(
            tenant_id=tenant_id,
            name="Tata Salt",
            sku=f"SKU-{uuid.uuid4().hex[:4].upper()}",
            selling_price=25.0,
            cost_price=20.0,
            is_active=True,
        )
        db.add(prod)
        db.flush()

        inv = Inventory(
            tenant_id=tenant_id,
            store_id=s1["id"],
            product_id=prod.id,
            quantity=100,
        )
        db.add(inv)
        db.commit()
        db.refresh(prod)
        product_id = prod.id
    finally:
        db.close()

    # Create a store transfer
    create_res = client.post(
        "/api/v1/store-transfers/",
        headers=headers,
        json={
            "source_store_id": s1["id"],
            "destination_store_id": s2["id"],
            "items": [
                {"product_id": product_id, "quantity": 5}
            ],
        },
    )
    assert create_res.status_code == 201, create_res.text
    transfer_data = create_res.json()
    transfer_id = transfer_data["id"]
    assert transfer_data["status"] == "Pending"
    assert transfer_data.get("rejection_reason") is None

    # Reject the transfer with rejection_reason
    rejection_reason_text = "Insufficient stock availability"
    reject_res = client.put(
        f"/api/v1/store-transfers/{transfer_id}/reject",
        headers=headers,
        json={"rejection_reason": rejection_reason_text},
    )
    assert reject_res.status_code == 200, reject_res.text
    rejected_data = reject_res.json()

    # 1. API Response body includes status: "Rejected" and rejection_reason
    assert rejected_data["status"] == "Rejected"
    assert rejected_data["rejection_reason"] == rejection_reason_text
    assert rejected_data["id"] == transfer_id
    assert rejected_data["source_store_id"] == s1["id"]
    assert rejected_data["destination_store_id"] == s2["id"]
    assert len(rejected_data["items"]) == 1
    assert rejected_data["items"][0]["product_id"] == product_id

    # 2. GET /api/v1/store-transfers/{id} returns the persisted rejection_reason
    get_res = client.get(f"/api/v1/store-transfers/{transfer_id}", headers=headers)
    assert get_res.status_code == 200, get_res.text
    get_data = get_res.json()
    assert get_data["status"] == "Rejected"
    assert get_data["rejection_reason"] == rejection_reason_text

    # 3. GET /api/v1/store-transfers/ list includes rejection_reason
    list_res = client.get(f"/api/v1/store-transfers/?status=Rejected", headers=headers)
    assert list_res.status_code == 200, list_res.text
    transfers_list = list_res.json()
    matching = [t for t in transfers_list if t["id"] == transfer_id]
    assert len(matching) == 1
    assert matching[0]["rejection_reason"] == rejection_reason_text

    # 4. Database persistence check
    db = SessionLocal()
    try:
        db_trf = db.query(StoreTransfer).filter(StoreTransfer.id == transfer_id).first()
        assert db_trf is not None
        assert db_trf.status == "Rejected"
        assert db_trf.rejection_reason == rejection_reason_text
    finally:
        db.close()


def test_reject_already_rejected_transfer_fails():
    """Verify that rejecting a non-pending transfer fails with 400."""
    ctx = _register_and_login("trfdbl")
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]

    s1 = _create_test_store(headers, "Source Branch Store", is_warehouse=False)
    s2 = _create_test_store(headers, "Destination Branch Store", is_warehouse=False)

    db = SessionLocal()
    try:
        prod = Product(
            tenant_id=tenant_id,
            name="Sample Product",
            sku=f"SKU-{uuid.uuid4().hex[:4].upper()}",
            selling_price=50.0,
            cost_price=40.0,
            is_active=True,
        )
        db.add(prod)
        db.flush()

        inv = Inventory(
            tenant_id=tenant_id,
            store_id=s1["id"],
            product_id=prod.id,
            quantity=50,
        )
        db.add(inv)
        db.commit()
        product_id = prod.id
    finally:
        db.close()

    create_res = client.post(
        "/api/v1/store-transfers/",
        headers=headers,
        json={
            "source_store_id": s1["id"],
            "destination_store_id": s2["id"],
            "items": [{"product_id": product_id, "quantity": 2}],
        },
    )
    transfer_id = create_res.json()["id"]

    # First rejection succeeds
    r1 = client.put(
        f"/api/v1/store-transfers/{transfer_id}/reject",
        headers=headers,
        json={"rejection_reason": "First rejection"},
    )
    assert r1.status_code == 200

    # Second rejection fails with 400
    r2 = client.put(
        f"/api/v1/store-transfers/{transfer_id}/reject",
        headers=headers,
        json={"rejection_reason": "Second rejection attempt"},
    )
    assert r2.status_code == 400
    assert "Only pending transfers can be rejected" in r2.text
