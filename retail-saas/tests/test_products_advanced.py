from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.product_variant import ProductVariant
from app.models.sale import Sale, SaleItem
from app.models.store import Store

client = TestClient(app)


def create_tenant_client(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    data = reg_resp.json()
    tenant_id = data["tenant_id"]

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
        "slug": slug,
    }


@pytest.fixture
def setup_product_data():
    t1 = create_tenant_client("prod-adv1")
    t2 = create_tenant_client("prod-adv2")
    db = SessionLocal()
    try:
        # Create store for t1
        s1 = Store(name="Main Store", code=f"ST-{t1['slug'][:6]}", tenant_id=t1["tenant_id"], is_active=True)
        # Create categories for t1 and t2
        cat1 = Category(name="Electronics", tenant_id=t1["tenant_id"], is_active=True)
        cat_t2 = Category(name="Other Tenant Cat", tenant_id=t2["tenant_id"], is_active=True)
        db.add_all([s1, cat1, cat_t2])
        db.commit()
        db.refresh(s1)
        db.refresh(cat1)
        db.refresh(cat_t2)

        return {
            "t1": t1,
            "t2": t2,
            "store": s1,
            "cat1": cat1,
            "cat_t2": cat_t2,
        }
    finally:
        db.close()


def test_search_products_returns_empty_list_when_no_match(setup_product_data):
    """Bug fix: Search must return 200 OK with empty list [] when nothing matches, not 404."""
    t1 = setup_product_data["t1"]
    resp = client.get(
        "/api/v1/products/search?search=NonExistentProductXYZ123",
        headers=t1["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_category_tenant_validation(setup_product_data):
    """Bug fix: Creating/updating product with foreign tenant's category must be rejected."""
    t1 = setup_product_data["t1"]
    cat_t2 = setup_product_data["cat_t2"]

    # Attempt cross-tenant category linking
    payload = {
        "name": "Cross Tenant Product",
        "sku": f"CT-{uuid.uuid4().hex[:6]}".upper(),
        "selling_price": "199.99",
        "price": "199.99",
        "category_id": cat_t2.id,
    }
    resp = client.post(
        "/api/v1/products",
        json=payload,
        headers=t1["headers"],
    )
    assert resp.status_code in [400, 404, 409], resp.text
    assert "category" in str(resp.json()).lower()


def test_product_response_rich_fields(setup_product_data):
    """Check that ProductResponse includes category_name and cost_price."""
    t1 = setup_product_data["t1"]
    cat1 = setup_product_data["cat1"]

    sku = f"RICH-{uuid.uuid4().hex[:6]}".upper()
    payload = {
        "name": "Smartphone Pro",
        "sku": sku,
        "selling_price": "29999.00",
        "price": "29999.00",
        "mrp": "34999.00",
        "category_id": cat1.id,
        "brand": "TechBrand",
    }
    resp = client.post(
        "/api/v1/products",
        json=payload,
        headers=t1["headers"],
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["sku"] == sku
    assert data["category_name"] == cat1.name
    assert "cost_price" in data


def test_list_products_filtering_and_sorting(setup_product_data):
    """Verify list_products filtering by category, brand, stock_status, price, and sorting."""
    t1 = setup_product_data["t1"]
    cat1 = setup_product_data["cat1"]

    # Create 2 products
    sku_a = f"FILTER-A-{uuid.uuid4().hex[:6]}".upper()
    sku_b = f"FILTER-B-{uuid.uuid4().hex[:6]}".upper()

    client.post("/api/v1/products", json={
        "name": "Alpha Earphones",
        "sku": sku_a,
        "selling_price": "500.00",
        "price": "500.00",
        "category_id": cat1.id,
        "brand": "AlphaBrand",
    }, headers=t1["headers"])

    client.post("/api/v1/products", json={
        "name": "Beta Headphones",
        "sku": sku_b,
        "selling_price": "1500.00",
        "price": "1500.00",
        "brand": "BetaBrand",
    }, headers=t1["headers"])

    # 1. Filter by category_id
    resp_cat = client.get(f"/api/v1/products?category_id={cat1.id}", headers=t1["headers"])
    assert resp_cat.status_code == 200
    cat_items = resp_cat.json()
    assert any(p["sku"] == sku_a for p in cat_items)
    assert not any(p["sku"] == sku_b for p in cat_items)

    # 2. Filter by brand
    resp_brand = client.get("/api/v1/products?brand=AlphaBrand", headers=t1["headers"])
    assert resp_brand.status_code == 200
    brand_items = resp_brand.json()
    assert all("alphabrand" in (p["brand"] or "").lower() for p in brand_items)

    # 3. Filter by price range
    resp_price = client.get("/api/v1/products?min_price=1000&max_price=2000", headers=t1["headers"])
    assert resp_price.status_code == 200
    price_items = resp_price.json()
    assert any(p["sku"] == sku_b for p in price_items)
    assert not any(p["sku"] == sku_a for p in price_items)

    # 4. Sorting price_asc
    resp_sort = client.get("/api/v1/products?sort_by=price_asc", headers=t1["headers"])
    assert resp_sort.status_code == 200


def test_catalog_summary_endpoint(setup_product_data):
    """Verify new GET /api/v1/products/summary endpoint."""
    t1 = setup_product_data["t1"]
    store = setup_product_data["store"]

    resp = client.get(f"/api/v1/products/summary?store_id={store.id}", headers=t1["headers"])
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert "total_products" in summary
    assert "active_products" in summary
    assert "total_inventory_cost_value" in summary
    assert "total_inventory_retail_value" in summary
    assert "category_breakdown" in summary


def test_bulk_create_products(setup_product_data):
    """Verify new POST /api/v1/products/bulk endpoint."""
    t1 = setup_product_data["t1"]
    sku1 = f"BULK-1-{uuid.uuid4().hex[:6]}".upper()
    sku2 = f"BULK-2-{uuid.uuid4().hex[:6]}".upper()

    payload = {
        "products": [
            {
                "name": "Bulk Product 1",
                "sku": sku1,
                "selling_price": "100.00",
                "price": "100.00",
            },
            {
                "name": "Bulk Product 2",
                "sku": sku2,
                "selling_price": "200.00",
                "price": "200.00",
            },
        ]
    }
    resp = client.post("/api/v1/products/bulk", json=payload, headers=t1["headers"])
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["total_created"] == 2
    skus = [p["sku"] for p in data["products"]]
    assert sku1 in skus
    assert sku2 in skus


def test_barcode_label_endpoint(setup_product_data):
    """Verify new GET /api/v1/products/{product_id}/barcode-label endpoint."""
    t1 = setup_product_data["t1"]
    store = setup_product_data["store"]

    sku = f"LBL-{uuid.uuid4().hex[:6]}".upper()
    c_resp = client.post("/api/v1/products", json={
        "name": "Thermal Label Item",
        "sku": sku,
        "selling_price": "450.00",
        "price": "450.00",
        "mrp": "500.00",
    }, headers=t1["headers"])
    assert c_resp.status_code == 201
    prod_id = c_resp.json()["id"]

    resp = client.get(
        f"/api/v1/products/{prod_id}/barcode-label?store_id={store.id}",
        headers=t1["headers"],
    )
    assert resp.status_code == 200, resp.text
    label = resp.json()
    assert label["product_id"] == prod_id
    assert label["sku"] == sku
    assert label["store_name"] == store.name
    assert label["barcode_image_base64"].startswith("data:image/png;base64,")


def test_lookup_barcode_resolves_product_and_variant(setup_product_data):
    """Verify barcode lookup resolves base product and variant barcode."""
    t1 = setup_product_data["t1"]
    db = SessionLocal()
    try:
        p_sku = f"BASE-{uuid.uuid4().hex[:6]}".upper()
        p_barcode = f"890{uuid.uuid4().int % 1000000000:09d}"
        var_barcode = f"890{uuid.uuid4().int % 1000000000:09d}"

        prod = Product(
            name="Polo T-Shirt",
            sku=p_sku,
            barcode=p_barcode,
            selling_price=Decimal("899.00"),
            tenant_id=t1["tenant_id"],
            is_active=True,
        )
        db.add(prod)
        db.commit()
        db.refresh(prod)

        variant = ProductVariant(
            tenant_id=t1["tenant_id"],
            product_id=prod.id,
            variant_name="Size XL",
            sku=f"{p_sku}-XL",
            barcode=var_barcode,
            selling_price=Decimal("949.00"),
            is_active=True,
        )
        db.add(variant)
        db.commit()

        # 1. Lookup base barcode
        r1 = client.get(f"/api/v1/products/barcode/{p_barcode}", headers=t1["headers"])
        assert r1.status_code == 200, r1.text
        assert r1.json()["id"] == prod.id

        # 2. Lookup variant barcode
        r2 = client.get(f"/api/v1/products/barcode/{var_barcode}", headers=t1["headers"])
        assert r2.status_code == 200, r2.text
        assert r2.json()["id"] == prod.id
    finally:
        db.close()


def test_delete_product_with_sales_history_rejected(setup_product_data):
    """Bug fix: Product with past sales cannot be hard deleted, returns 400 Bad Request."""
    t1 = setup_product_data["t1"]
    store = setup_product_data["store"]
    db = SessionLocal()
    try:
        prod = Product(
            name="Sold Product",
            sku=f"SOLD-{uuid.uuid4().hex[:6]}".upper(),
            selling_price=Decimal("150.00"),
            tenant_id=t1["tenant_id"],
            is_active=True,
        )
        db.add(prod)
        db.commit()
        db.refresh(prod)

        # Create a sale record referencing this product
        sale = Sale(
            tenant_id=t1["tenant_id"],
            store_id=store.id,
            sale_number=f"SALE-{uuid.uuid4().hex[:8]}",
            subtotal=Decimal("150.00"),
            total_amount=Decimal("150.00"),
            payment_method="CASH",
        )
        db.add(sale)
        db.flush()

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=prod.id,
            quantity=1,
            unit_price=Decimal("150.00"),
            total_price=Decimal("150.00"),
        )
        db.add(sale_item)
        db.commit()

        # Attempt DELETE product
        del_resp = client.delete(f"/api/v1/products/{prod.id}", headers=t1["headers"])
        assert del_resp.status_code == 400, del_resp.text
        assert "cannot delete product" in del_resp.json()["detail"].lower()
    finally:
        db.close()


def test_delete_product_without_history_succeeds(setup_product_data):
    """Product without transaction history can be deleted safely."""
    t1 = setup_product_data["t1"]

    sku = f"SAFE-DEL-{uuid.uuid4().hex[:6]}".upper()
    c_resp = client.post("/api/v1/products", json={
        "name": "Deletable Item",
        "sku": sku,
        "selling_price": "75.00",
        "price": "75.00",
    }, headers=t1["headers"])
    assert c_resp.status_code == 201
    prod_id = c_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/products/{prod_id}", headers=t1["headers"])
    assert del_resp.status_code == 204


def test_expiring_soon_returns_real_expiring_products(setup_product_data):
    """Bug fix: list_expiring_soon must return products expiring within cutoff."""
    t1 = setup_product_data["t1"]
    store = setup_product_data["store"]
    db = SessionLocal()
    try:
        today = date.today()
        exp_prod = Product(
            name="Milk Carton 1L",
            sku=f"MILK-{uuid.uuid4().hex[:6]}".upper(),
            selling_price=Decimal("60.00"),
            tenant_id=t1["tenant_id"],
            track_expiry=True,
            expiry_date=today + timedelta(days=5),
            is_active=True,
        )
        safe_prod = Product(
            name="Salt Pack 1kg",
            sku=f"SALT-{uuid.uuid4().hex[:6]}".upper(),
            selling_price=Decimal("20.00"),
            tenant_id=t1["tenant_id"],
            track_expiry=True,
            expiry_date=today + timedelta(days=120),
            is_active=True,
        )
        db.add_all([exp_prod, safe_prod])
        db.commit()
        db.refresh(exp_prod)
        db.refresh(safe_prod)

        resp = client.get(
            f"/api/v1/products/expiring-soon?store_id={store.id}&days=10",
            headers=t1["headers"],
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()
        ids = [p["id"] for p in items]
        assert exp_prod.id in ids
        assert safe_prod.id not in ids
    finally:
        db.close()
