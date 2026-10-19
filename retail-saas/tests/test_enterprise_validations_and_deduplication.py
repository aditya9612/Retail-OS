import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.user import User

client = TestClient(app)


def create_tenant_client(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Enterprise Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
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

    # Create stores
    s1 = Store(name=f"Main Store {slug[:4]}", code=f"MS-{slug[:4].upper()}", tenant_id=tenant_id, is_active=True)
    s2 = Store(name=f"Branch Store {slug[:4]}", code=f"BS-{slug[:4].upper()}", tenant_id=tenant_id, is_active=True)
    db.add_all([s1, s2])
    db.flush()

    # Create supplier
    supp = Supplier(
        name=f"Enterprise Supplier {slug[:4]}",
        tenant_id=tenant_id,
        phone="9876543210",
        contact_person="Director",
        gstin="27AAPFU0939F1ZV",
        is_active=True,
    )
    db.add(supp)
    db.flush()

    # Create products
    p1 = Product(name=f"Product A {slug[:4]}", sku=f"SKU-A-{slug[:6].upper()}", tenant_id=tenant_id, selling_price=100.0, is_active=True)
    p2 = Product(name=f"Product B {slug[:4]}", sku=f"SKU-B-{slug[:6].upper()}", tenant_id=tenant_id, selling_price=200.0, is_active=True)
    db.add_all([p1, p2])
    db.commit()

    s1_id, s2_id = s1.id, s2.id
    supp_id = supp.id
    p1_id, p2_id = p1.id, p2.id
    db.close()

    return {
        "tenant_id": tenant_id,
        "headers": headers,
        "s1_id": s1_id,
        "s2_id": s2_id,
        "supp_id": supp_id,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "slug": slug,
    }


# =====================================================================
# 1. PURCHASE ORDER DEDUPLICATION & ENTERPRISE VALIDATIONS
# =====================================================================

def test_po_empty_items_and_duplicate_product_lines_rejected():
    tc = create_tenant_client("po-items")
    headers, s1_id, supp_id, p1_id = tc["headers"], tc["s1_id"], tc["supp_id"], tc["p1_id"]

    # 1. Empty items list (schema validation)
    r1 = client.post(
        "/api/v1/purchase-orders",
        json={"supplier_id": supp_id, "store_id": s1_id, "items": []},
        headers=headers,
    )
    assert r1.status_code in (400, 409, 422)
    assert "at least one" in r1.text.lower()

    # 2. Duplicate product line in same PO
    r2 = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supp_id,
            "store_id": s1_id,
            "items": [
                {"product_id": p1_id, "quantity": 5, "unit_cost": 50.0},
                {"product_id": p1_id, "quantity": 10, "unit_cost": 50.0},
            ],
        },
        headers=headers,
    )
    assert r2.status_code == 409
    assert "duplicate product" in r2.text.lower()


def test_po_duplicate_invoice_number_and_double_click_prevention():
    tc = create_tenant_client("po-inv")
    headers, s1_id, supp_id, p1_id, p2_id = (
        tc["headers"],
        tc["s1_id"],
        tc["supp_id"],
        tc["p1_id"],
        tc["p2_id"],
    )

    invoice_no = f"INV-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create first PO with invoice_number
    r1 = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supp_id,
            "store_id": s1_id,
            "invoice_number": invoice_no,
            "items": [{"product_id": p1_id, "quantity": 5, "unit_cost": 50.0}],
        },
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    po1_id = r1.json()["id"]

    # 1b. Immediate double-click submission with same items -> 409 Conflict (anti-double-click)
    r_double_click = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supp_id,
            "store_id": s1_id,
            "items": [{"product_id": p1_id, "quantity": 5, "unit_cost": 50.0}],
        },
        headers=headers,
    )
    assert r_double_click.status_code == 409
    assert "duplicate purchase order submission" in r_double_click.text.lower() or "identical" in r_double_click.text.lower()

    # 2. Try creating duplicate PO with exact same invoice number for same supplier -> 409 Conflict
    r2 = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supp_id,
            "store_id": s1_id,
            "invoice_number": invoice_no,
            "items": [{"product_id": p2_id, "quantity": 8, "unit_cost": 60.0}],
        },
        headers=headers,
    )
    assert r2.status_code == 409
    assert "already exists for this supplier" in r2.text

    # 3. Create second PO with unique invoice and product p2
    inv2 = f"INV-2-{uuid.uuid4().hex[:6].upper()}"
    r3 = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supp_id,
            "store_id": s1_id,
            "invoice_number": inv2,
            "items": [{"product_id": p2_id, "quantity": 2, "unit_cost": 50.0}],
        },
        headers=headers,
    )
    assert r3.status_code == 201
    po2_id = r3.json()["id"]

    # 4. Attempt to update po2's invoice to po1's invoice -> 409 Conflict
    r4 = client.patch(
        f"/api/v1/purchase-orders/{po2_id}",
        json={"invoice_number": invoice_no},
        headers=headers,
    )
    assert r4.status_code == 409
    assert "already exists for this supplier" in r4.text


# =====================================================================
# 2. STORE TRANSFER DEDUPLICATION & VALIDATIONS
# =====================================================================

def test_store_transfer_duplicate_items_and_double_click_prevention():
    tc = create_tenant_client("trf-dedup")
    headers, s1_id, s2_id, p1_id, p2_id = (
        tc["headers"],
        tc["s1_id"],
        tc["s2_id"],
        tc["p1_id"],
        tc["p2_id"],
    )

    # 1. Transfer with duplicate product line
    r1 = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [
                {"product_id": p1_id, "quantity": 5},
                {"product_id": p1_id, "quantity": 10},
            ],
        },
        headers=headers,
    )
    assert r1.status_code in (400, 422)
    assert "duplicate product" in r1.text.lower()

    # 2. Valid transfer creation
    r2 = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [{"product_id": p1_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert r2.status_code == 201, r2.text

    # 3. Immediate duplicate submission (anti-double-click)
    r3 = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": s1_id,
            "destination_store_id": s2_id,
            "items": [{"product_id": p1_id, "quantity": 5}],
        },
        headers=headers,
    )
    assert r3.status_code == 400
    assert "duplicate transfer" in r3.text.lower() or "identical" in r3.text.lower()


# =====================================================================
# 3. PRODUCT VARIANT ATTRIBUTE MATRIX DEDUPLICATION
# =====================================================================

def test_product_variant_duplicate_combination_and_name_prevention():
    tc = create_tenant_client("var-dedup")
    headers, p1_id = tc["headers"], tc["p1_id"]

    sku1 = f"VAR-{uuid.uuid4().hex[:6].upper()}"
    sku2 = f"VAR-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create first variant with size='XL' and color='Black'
    r1 = client.post(
        f"/api/v1/products/{p1_id}/variants",
        json={
            "variant_name": "Premium Black XL",
            "sku": sku1,
            "size": "XL",
            "color": "Black",
            "selling_price": "199.00",
        },
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    var1_id = r1.json()["id"]

    # 2. Try creating second variant with same (size='XL', color='Black') -> 409 Conflict
    r2 = client.post(
        f"/api/v1/products/{p1_id}/variants",
        json={
            "variant_name": "Another Variant",
            "sku": sku2,
            "size": "XL",
            "color": "Black",
            "selling_price": "199.00",
        },
        headers=headers,
    )
    assert r2.status_code == 409
    assert "already exists for this product" in r2.text

    # 3. Try creating second variant with same variant_name -> 409 Conflict
    sku3 = f"VAR-{uuid.uuid4().hex[:6].upper()}"
    r3 = client.post(
        f"/api/v1/products/{p1_id}/variants",
        json={
            "variant_name": "Premium Black XL",
            "sku": sku3,
            "size": "M",
            "color": "Red",
            "selling_price": "199.00",
        },
        headers=headers,
    )
    assert r3.status_code == 409
    assert "already exists for this product" in r3.text


# =====================================================================
# 4. WAREHOUSE DEDUPLICATION (NAME & CODE)
# =====================================================================

def test_warehouse_duplicate_name_prevention():
    tc = create_tenant_client("wh-dedup")
    headers, s1_id = tc["headers"], tc["s1_id"]

    c1 = f"WH-{uuid.uuid4().hex[:6].upper()}"
    c2 = f"WH-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create Warehouse Alpha
    r1 = client.post(
        "/api/v1/warehouses",
        json={"name": "Regional Logistics Hub", "code": c1, "store_id": s1_id},
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    w1_id = r1.json()["id"]

    # 2. Try creating warehouse with duplicate name (different code) -> 409 Conflict
    r2 = client.post(
        "/api/v1/warehouses",
        json={"name": "regional logistics hub", "code": c2, "store_id": s1_id},
        headers=headers,
    )
    assert r2.status_code == 409
    assert "already exists" in r2.text

    # 3. Create Warehouse Beta with unique name
    c3 = f"WH-{uuid.uuid4().hex[:6].upper()}"
    r3 = client.post(
        "/api/v1/warehouses",
        json={"name": "Express Fulfillment Hub", "code": c3, "store_id": s1_id},
        headers=headers,
    )
    assert r3.status_code == 201
    w3_id = r3.json()["id"]

    # 4. Try updating Warehouse Beta to have Warehouse Alpha's name -> 409 Conflict
    r4 = client.patch(
        f"/api/v1/warehouses/{w3_id}",
        json={"name": "Regional Logistics Hub"},
        headers=headers,
    )
    assert r4.status_code == 409
    assert "already exists" in r4.text


# =====================================================================
# 5. SUPPLIER DEDUPLICATION (PHONE & GSTIN)
# =====================================================================

def test_supplier_duplicate_phone_prevention():
    tc = create_tenant_client("sup-phone")
    headers = tc["headers"]

    # 1. Create first supplier with phone 9822114433
    r1 = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Western Spices Pvt Ltd",
            "phone": "9822114433",
            "contact_person": "Ajay Patil",
        },
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    s1_id = r1.json()["id"]

    # 2. Try creating second supplier with exact same phone in same tenant -> 409 Conflict
    r2 = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Western Grocery Stores",
            "phone": "9822114433",
            "contact_person": "Sunil Patil",
        },
        headers=headers,
    )
    assert r2.status_code == 409
    assert "already exists" in r2.text

    # 3. Create second supplier with unique phone
    r3 = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Western Grocery Stores",
            "phone": "9822114455",
            "contact_person": "Sunil Patil",
        },
        headers=headers,
    )
    assert r3.status_code == 201
    s2_id = r3.json()["id"]

    # 4. Update second supplier to have first supplier's phone -> 409 Conflict
    r4 = client.patch(
        f"/api/v1/suppliers/{s2_id}",
        json={"phone": "9822114433"},
        headers=headers,
    )
    assert r4.status_code == 409
    assert "already exists" in r4.text
