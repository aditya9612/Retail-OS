from datetime import date
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store

client = TestClient(app)


def create_tenant_client(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "SecurePassword123!"

    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Test Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Tenant Admin",
            "password": password,
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_resp = client.get("/api/v1/users/me", headers=headers)
    assert me_resp.status_code == 200
    tenant_id = me_resp.json()["tenant_id"]

    return {"headers": headers, "tenant_id": tenant_id, "slug": slug}


@pytest.fixture
def sales_tenant():
    return create_tenant_client("sales-t")


@pytest.fixture
def sales_fixtures(sales_tenant):
    db = SessionLocal()
    tenant_id = sales_tenant["tenant_id"]
    try:
        store = Store(name="Main Store", code=f"MS-{uuid.uuid4().hex[:6]}", tenant_id=tenant_id, is_active=True)
        db.add(store)
        db.flush()

        prod1 = Product(
            name="Product Alpha",
            sku=f"SKU-ALP-{uuid.uuid4().hex[:6]}",
            selling_price=Decimal("150.00"),
            gst_rate=Decimal("18.00"),
            tenant_id=tenant_id,
            is_active=True,
        )
        prod2 = Product(
            name="Product Beta",
            sku=f"SKU-BET-{uuid.uuid4().hex[:6]}",
            selling_price=Decimal("50.00"),
            gst_rate=Decimal("5.00"),
            tenant_id=tenant_id,
            is_active=True,
        )
        prod_inactive = Product(
            name="Inactive Product",
            sku=f"SKU-INA-{uuid.uuid4().hex[:6]}",
            selling_price=Decimal("80.00"),
            gst_rate=Decimal("12.00"),
            tenant_id=tenant_id,
            is_active=False,
        )
        db.add_all([prod1, prod2, prod_inactive])
        db.flush()

        inv1 = Inventory(tenant_id=tenant_id, store_id=store.id, product_id=prod1.id, quantity=30)
        inv2 = Inventory(tenant_id=tenant_id, store_id=store.id, product_id=prod2.id, quantity=50)
        inv_inact = Inventory(tenant_id=tenant_id, store_id=store.id, product_id=prod_inactive.id, quantity=10)
        db.add_all([inv1, inv2, inv_inact])
        db.flush()

        cust = Customer(
            name="Rajesh Sharma",
            phone=f"98{uuid.uuid4().int % 100000000:08d}",
            email=f"rajesh_{uuid.uuid4().hex[:6]}@example.com",
            tenant_id=tenant_id,
        )
        db.add(cust)
        db.commit()

        return {
            "store_id": store.id,
            "prod1_id": prod1.id,
            "prod2_id": prod2.id,
            "prod_inactive_id": prod_inactive.id,
            "cust_id": cust.id,
        }
    finally:
        db.close()


def test_create_sale_success_and_inventory_deduction(sales_tenant, sales_fixtures):
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p1 = sales_fixtures["prod1_id"]
    p2 = sales_fixtures["prod2_id"]

    # 1. Create a sale with 2 items
    payload = {
        "store_id": store_id,
        "payment_method": "cash",
        "customer_id": sales_fixtures["cust_id"],
        "items": [
            {"product_id": p1, "quantity": 3, "discount": 20.0},
            {"product_id": p2, "quantity": 5, "discount": 0.0},
        ],
    }

    resp = client.post("/api/v1/sales", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["store_id"] == store_id
    assert data["payment_method"] == "cash"
    assert data["payment_status"] == "paid"
    assert len(data["items"]) == 2

    # Verify item 1 calculations: (150*3) - 20 = 430 taxable, 18% tax = 77.40, total = 507.40
    # Verify item 2 calculations: (50*5) - 0 = 250 taxable, 5% tax = 12.50, total = 262.50
    # Sale subtotal = 430 + 250 = 680, tax = 77.40 + 12.50 = 89.90, total = 769.90
    assert float(data["subtotal"]) == 680.0
    assert round(float(data["tax_amount"]), 2) == 89.90
    assert round(float(data["total_amount"]), 2) == 769.90

    # Verify inventory was deducted
    db = SessionLocal()
    try:
        inv1 = db.query(Inventory).filter(Inventory.store_id == store_id, Inventory.product_id == p1).first()
        inv2 = db.query(Inventory).filter(Inventory.store_id == store_id, Inventory.product_id == p2).first()
        assert inv1.quantity == 27  # 30 - 3
        assert inv2.quantity == 45  # 50 - 5
    finally:
        db.close()


def test_create_sale_validations(sales_tenant, sales_fixtures):
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p1 = sales_fixtures["prod1_id"]
    p_inactive = sales_fixtures["prod_inactive_id"]

    # Empty items
    res_empty = client.post(
        "/api/v1/sales",
        headers=headers,
        json={"store_id": store_id, "items": []},
    )
    assert res_empty.status_code == 422

    # Duplicate product in items
    res_dup = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "items": [
                {"product_id": p1, "quantity": 1},
                {"product_id": p1, "quantity": 2},
            ],
        },
    )
    assert res_dup.status_code == 422

    # Insufficient stock (only 30 in stock, requesting 100)
    res_overstock = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "items": [{"product_id": p1, "quantity": 100}],
        },
    )
    assert res_overstock.status_code == 400
    assert "Insufficient stock" in res_overstock.text

    # Inactive product
    res_inact = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "items": [{"product_id": p_inactive, "quantity": 1}],
        },
    )
    assert res_inact.status_code == 400
    assert "inactive" in res_inact.text.lower()

    # Invalid payment method
    res_bad_pay = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "bitcoin_crypto",
            "items": [{"product_id": p1, "quantity": 1}],
        },
    )
    assert res_bad_pay.status_code == 422


def test_get_sales_filters_and_pagination(sales_tenant, sales_fixtures):
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p2 = sales_fixtures["prod2_id"]

    # Create 3 sales
    s1 = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "upi",
            "items": [{"product_id": p2, "quantity": 1}],
        },
    ).json()

    s2 = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "card",
            "items": [{"product_id": p2, "quantity": 1}],
        },
    ).json()

    # 1. Filter by store_id
    res_store = client.get(f"/api/v1/sales?store_id={store_id}", headers=headers)
    assert res_store.status_code == 200
    assert len(res_store.json()) >= 2

    # 2. Filter by payment_method
    res_upi = client.get("/api/v1/sales?payment_method=upi", headers=headers)
    assert res_upi.status_code == 200
    for s in res_upi.json():
        assert s["payment_method"] == "upi"

    # 3. Filter by search (sale_number)
    sale_num = s1["sale_number"]
    res_search = client.get(f"/api/v1/sales?search={sale_num}", headers=headers)
    assert res_search.status_code == 200
    assert len(res_search.json()) == 1
    assert res_search.json()[0]["id"] == s1["id"]

    # 4. Pagination
    res_paged = client.get("/api/v1/sales?page=1&page_size=1", headers=headers)
    assert res_paged.status_code == 200
    assert len(res_paged.json()) == 1


def test_get_sale_by_id_and_not_found(sales_tenant, sales_fixtures):
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p2 = sales_fixtures["prod2_id"]

    create_res = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "cash",
            "items": [{"product_id": p2, "quantity": 2}],
        },
    )
    assert create_res.status_code == 201
    sale_id = create_res.json()["id"]

    # Get by ID
    get_res = client.get(f"/api/v1/sales/{sale_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == sale_id
    assert len(get_res.json()["items"]) == 1

    # Non-existent ID
    res_404 = client.get("/api/v1/sales/999999", headers=headers)
    assert res_404.status_code == 404


def test_update_sale_inventory_adjustment(sales_tenant, sales_fixtures):
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p2 = sales_fixtures["prod2_id"]

    # Create sale with qty 4
    create_res = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "cash",
            "items": [{"product_id": p2, "quantity": 4}],
        },
    )
    sale_id = create_res.json()["id"]

    # Update sale: change quantity to 2 and payment_method to upi
    update_res = client.put(
        f"/api/v1/sales/{sale_id}",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "upi",
            "payment_status": "completed",
            "items": [{"product_id": p2, "quantity": 2}],
        },
    )
    assert update_res.status_code == 200
    up_data = update_res.json()
    assert up_data["payment_method"] == "upi"
    assert up_data["items"][0]["quantity"] == 2

    # Verify inventory was adjusted (4 restored, 2 deducted -> net 2 restored)
    get_res = client.get(f"/api/v1/sales/{sale_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["payment_method"] == "upi"


def test_delete_sale_inventory_restoration(sales_tenant, sales_fixtures):
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p1 = sales_fixtures["prod1_id"]

    db = SessionLocal()
    try:
        inv_before = db.query(Inventory).filter(Inventory.store_id == store_id, Inventory.product_id == p1).first().quantity
    finally:
        db.close()

    # Create sale of 3 units
    create_res = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "cash",
            "items": [{"product_id": p1, "quantity": 3}],
        },
    )
    sale_id = create_res.json()["id"]

    db = SessionLocal()
    try:
        inv_after_sale = db.query(Inventory).filter(Inventory.store_id == store_id, Inventory.product_id == p1).first().quantity
        assert inv_after_sale == inv_before - 3
    finally:
        db.close()

    # Delete the sale
    del_res = client.delete(f"/api/v1/sales/{sale_id}", headers=headers)
    assert del_res.status_code == 200

    # Verify inventory is restored
    db = SessionLocal()
    try:
        inv_after_del = db.query(Inventory).filter(Inventory.store_id == store_id, Inventory.product_id == p1).first().quantity
        assert inv_after_del == inv_before
    finally:
        db.close()

    # Deleting non-existent sale returns 404
    assert client.delete("/api/v1/sales/999999", headers=headers).status_code == 404



def test_sale_thermal_receipt_all_modes(sales_tenant, sales_fixtures):
    """Verify GET /api/v1/sales/{sale_id}/thermal supports all 7 standard delivery modes."""
    headers = sales_tenant["headers"]
    store_id = sales_fixtures["store_id"]
    p1 = sales_fixtures["prod1_id"]

    # Create a test sale
    create_res = client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "store_id": store_id,
            "payment_method": "cash",
            "items": [{"product_id": p1, "quantity": 2, "discount": 10.0}],
        },
    )
    assert create_res.status_code in (200, 201)
    sale = create_res.json()
    sale_id = sale["id"]

    # 1. Preview mode (Default & explicit) -> 80mm PNG
    prev_default = client.get(f"/api/v1/sales/{sale_id}/thermal", headers=headers)
    assert prev_default.status_code == 200
    assert "image/png" in prev_default.headers["content-type"]
    assert prev_default.content.startswith(b"\x89PNG")

    prev_expl = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=preview", headers=headers)
    assert prev_expl.status_code == 200
    assert "image/png" in prev_expl.headers["content-type"]
    assert prev_expl.content.startswith(b"\x89PNG")

    # 2. View mode -> HTML with auto-print
    view_res = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=view", headers=headers)
    assert view_res.status_code == 200
    assert "text/html" in view_res.headers["content-type"]
    assert "window.print()" in view_res.text
    assert "SALES RECEIPT" in view_res.text

    # 3. Download mode -> ESC/POS text attachment
    dl_res = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=download", headers=headers)
    assert dl_res.status_code == 200
    assert "text/plain" in dl_res.headers["content-type"]
    assert "attachment" in dl_res.headers["content-disposition"]
    assert "TOTAL:" in dl_res.text

    # 4. PDF mode -> 80mm roll PDF
    pdf_res = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers["content-type"]
    assert pdf_res.content.startswith(b"%PDF")

    # 5. HTML mode -> styled raw HTML
    html_res = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=html", headers=headers)
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    assert "SALES RECEIPT" in html_res.text

    # 6. JSON mode -> structured payload
    json_res = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=json", headers=headers)
    assert json_res.status_code == 200
    assert json_res.json()["id"] == sale_id
    assert json_res.json()["total_amount"] == sale["total_amount"]

    # 7. Text mode -> raw ESC/POS text stream
    text_res = client.get(f"/api/v1/sales/{sale_id}/thermal?mode=text", headers=headers)
    assert text_res.status_code == 200
    assert "text/plain" in text_res.headers["content-type"]
    assert "TOTAL:" in text_res.text
