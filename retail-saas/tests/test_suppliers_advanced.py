import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.store import Store
from app.models.supplier import Supplier

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"supadv-{uuid.uuid4().hex[:8]}"
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


def test_partial_and_multi_field_search(tenant_fixture):
    headers = tenant_fixture["headers"]

    create_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Metro Electronics Wholesalers",
            "contact_person": "Rohan Sharma",
            "email": "rohan.sharma@gmail.com",
            "phone": "9876543210",
            "address": "Lamington Road, Mumbai",
            "gstin": "27AAPFU0939F1ZV",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    sup_id = create_resp.json()["id"]

    # 1. Partial name search
    res1 = client.get("/api/v1/suppliers/search?search=Electronics", headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert any(s["id"] == sup_id for s in data1)

    # 2. Search by contact person
    res2 = client.get("/api/v1/suppliers/search?search=Rohan", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert any(s["id"] == sup_id for s in data2)

    # 3. Search by phone number
    res3 = client.get("/api/v1/suppliers/search?search=987654", headers=headers)
    assert res3.status_code == 200
    data3 = res3.json()
    assert any(s["id"] == sup_id for s in data3)

    # 4. Search by GSTIN
    res4 = client.get("/api/v1/suppliers/search?search=AAPFU09", headers=headers)
    assert res4.status_code == 200
    data4 = res4.json()
    assert any(s["id"] == sup_id for s in data4)


def test_supplier_duplicate_prevention(tenant_fixture):
    headers = tenant_fixture["headers"]

    # 1. Create first supplier
    sup1 = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Bharat Spices Co",
            "contact_person": "Sunil Joshi",
            "email": "sunil.joshi@gmail.com",
            "phone": "9876543210",
            "address": "APMC Market, Vashi",
            "gstin": "27AAPFU0939F1ZV",
        },
        headers=headers,
    )
    assert sup1.status_code == 201, sup1.text

    # 2. Duplicate name creation -> 409 Conflict
    sup_dup_name = client.post(
        "/api/v1/suppliers",
        json={
            "name": "bharat spices co",
            "phone": "9822334455",
        },
        headers=headers,
    )
    assert sup_dup_name.status_code == 409
    assert "already exists" in sup_dup_name.text

    # 3. Duplicate GSTIN creation -> 409 Conflict
    sup_dup_gstin = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Unique Name Traders",
            "phone": "9822334455",
            "gstin": "27AAPFU0939F1ZV",
        },
        headers=headers,
    )
    assert sup_dup_gstin.status_code == 409
    assert "already exists" in sup_dup_gstin.text

    # 4. Create second supplier with different name & GSTIN
    sup2 = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Unique Name Traders",
            "phone": "9822334455",
        },
        headers=headers,
    )
    assert sup2.status_code == 201
    sup2_id = sup2.json()["id"]

    # 5. Update sup2 to have sup1's name -> 409 Conflict
    up_dup_name = client.patch(
        f"/api/v1/suppliers/{sup2_id}",
        json={"name": "Bharat Spices Co"},
        headers=headers,
    )
    assert up_dup_name.status_code == 409

    # 6. Update sup2 to have sup1's GSTIN -> 409 Conflict
    up_dup_gstin = client.patch(
        f"/api/v1/suppliers/{sup2_id}",
        json={"gstin": "27AAPFU0939F1ZV"},
        headers=headers,
    )
    assert up_dup_gstin.status_code == 409


def test_supplier_delete_success_and_protection(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    # 1. Create a supplier without POs
    sup_free = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Temporary Supplier",
            "phone": "9811223344",
        },
        headers=headers,
    ).json()
    free_id = sup_free["id"]

    # 2. Delete succeeds
    del_resp = client.delete(f"/api/v1/suppliers/{free_id}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    del_data = del_resp.json()
    assert del_data["success"] is True
    assert del_data["data"]["id"] == free_id

    # 3. Getting deleted supplier returns 404
    get_del = client.get(f"/api/v1/suppliers/{free_id}", headers=headers)
    assert get_del.status_code == 404

    # 4. Create a supplier and attach a PO
    sup_busy = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Busy Supplier With Orders",
            "phone": "9811223355",
        },
        headers=headers,
    ).json()
    busy_id = sup_busy["id"]

    db = SessionLocal()
    store = Store(tenant_id=tenant_id, name="Main Store", code=f"MS-{uuid.uuid4().hex[:4]}")
    db.add(store)
    db.commit()
    db.refresh(store)

    po = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=busy_id,
        store_id=store.id,
        po_number=f"PO-{uuid.uuid4().hex[:6]}",
        status="received",
        total_amount=Decimal("500.00"),
    )
    db.add(po)
    db.commit()
    db.close()

    # 5. Attempting to delete supplier with POs returns 409 Conflict
    del_busy = client.delete(f"/api/v1/suppliers/{busy_id}", headers=headers)
    assert del_busy.status_code == 409
    assert "purchase order" in del_busy.text.lower()


def test_supplier_products_catalog(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    # 1. Create supplier
    sup = client.post(
        "/api/v1/suppliers",
        json={"name": "Hardware Supplies Mart", "phone": "9876543299"},
        headers=headers,
    ).json()
    sup_id = sup["id"]

    # Initially 0 products
    cat_empty = client.get(f"/api/v1/suppliers/{sup_id}/products", headers=headers)
    assert cat_empty.status_code == 200
    assert cat_empty.json()["total_products"] == 0
    assert cat_empty.json()["data"] == []

    # 2. Attach store, products, and PO
    db = SessionLocal()
    store = Store(tenant_id=tenant_id, name="HW Store", code=f"HWS-{uuid.uuid4().hex[:4]}")
    p1 = Product(tenant_id=tenant_id, name="Hammer Pro", sku=f"HAM-{uuid.uuid4().hex[:4]}", price=Decimal("150.00"), cost_price=Decimal("100.00"))
    p2 = Product(tenant_id=tenant_id, name="Screwdriver Set", sku=f"SCR-{uuid.uuid4().hex[:4]}", price=Decimal("80.00"), cost_price=Decimal("50.00"))
    db.add_all([store, p1, p2])
    db.commit()

    po = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=sup_id,
        store_id=store.id,
        po_number=f"PO-{uuid.uuid4().hex[:6]}",
        status="received",
        total_amount=Decimal("1500.00"),
    )
    db.add(po)
    db.commit()

    item1 = PurchaseOrderItem(purchase_order_id=po.id, product_id=p1.id, quantity=10, unit_price=Decimal("100.00"), total=Decimal("1000.00"))
    item2 = PurchaseOrderItem(purchase_order_id=po.id, product_id=p2.id, quantity=10, unit_price=Decimal("50.00"), total=Decimal("500.00"))
    db.add_all([item1, item2])
    db.commit()
    db.close()

    # 3. Call supplier products catalog
    cat_resp = client.get(f"/api/v1/suppliers/{sup_id}/products", headers=headers)
    assert cat_resp.status_code == 200, cat_resp.text
    cat_data = cat_resp.json()
    assert cat_data["success"] is True
    assert cat_data["supplier_id"] == sup_id
    assert cat_data["total_products"] == 2
    prods = cat_data["data"]
    assert len(prods) == 2
    assert any(p["product_name"] == "Hammer Pro" and p["total_quantity_purchased"] == 10 for p in prods)
    assert any(p["product_name"] == "Screwdriver Set" and p["total_quantity_purchased"] == 10 for p in prods)


def test_suppliers_summary(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Call summary endpoint
    resp = client.get("/api/v1/suppliers/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert "total_suppliers" in data
    assert "active_suppliers" in data
    assert "inactive_suppliers" in data
    assert "total_spend" in data
    assert "pending_orders_count" in data
    assert "top_suppliers" in data
    assert isinstance(data["top_suppliers"], list)


def test_list_suppliers_pagination_and_filters(tenant_fixture):
    headers = tenant_fixture["headers"]

    s1 = client.post("/api/v1/suppliers", json={"name": "Alpha Corp", "phone": "9811000001"}, headers=headers).json()
    s2 = client.post("/api/v1/suppliers", json={"name": "Beta Enterprises", "phone": "9811000002"}, headers=headers).json()
    s3 = client.post("/api/v1/suppliers", json={"name": "Gamma Solutions", "phone": "9811000003"}, headers=headers).json()

    # Deactivate s3
    client.patch(f"/api/v1/suppliers/{s3['id']}/status", json={"is_active": False}, headers=headers)

    # 1. Filter active only
    act_resp = client.get("/api/v1/suppliers?is_active=true", headers=headers)
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert all(s["is_active"] is True for s in act_data)
    assert any(s["id"] == s1["id"] for s in act_data)
    assert not any(s["id"] == s3["id"] for s in act_data)

    # 2. Filter inactive only
    inact_resp = client.get("/api/v1/suppliers?is_active=false", headers=headers)
    assert inact_resp.status_code == 200
    inact_data = inact_resp.json()
    assert any(s["id"] == s3["id"] for s in inact_data)
    assert not any(s["id"] == s1["id"] for s in inact_data)

    # 3. Pagination
    page_resp = client.get("/api/v1/suppliers?page=1&page_size=2", headers=headers)
    assert page_resp.status_code == 200
    page_data = page_resp.json()
    assert len(page_data) == 2

    # 4. Search in list
    srch_resp = client.get("/api/v1/suppliers?search=Alpha", headers=headers)
    assert srch_resp.status_code == 200
    srch_data = srch_resp.json()
    assert len(srch_data) >= 1
    assert any(s["name"] == "Alpha Corp" for s in srch_data)

