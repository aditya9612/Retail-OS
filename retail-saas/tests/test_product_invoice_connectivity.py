from datetime import date, timedelta
from decimal import Decimal
import io
import json
import uuid

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.product_variant import ProductVariant
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.storefront import StorefrontCheckoutRequest
from app.services.storefront_service import StorefrontService

client = TestClient(app)


def _create_admin_session(prefix: str):
    uid = uuid.uuid4().hex[:8]
    slug = f"{prefix}-{uid}"
    email = f"{prefix}-{uid}@test.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Admin User",
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

    store_resp = client.post(
        "/api/v1/stores",
        json={"name": f"Main Store {uid}", "code": f"MS{uid[:4].upper()}"},
        headers=headers,
    )
    assert store_resp.status_code == 201, store_resp.text
    store = store_resp.json()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        tenant_id = user.tenant_id
        user_id = user.id
    finally:
        db.close()

    return {
        "headers": headers,
        "store": store,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "uid": uid,
    }


def test_product_create_update_lookup_connectivity():
    """Verify cost_price, zero gst_rate, variants persistence, and opening stock seeding on product APIs."""
    env = _create_admin_session("prdconn")
    headers = env["headers"]
    store_id = env["store"]["id"]
    uid = env["uid"]
    barcode_main = f"89077{int(uid[:6], 16) % 10000000:07d}"
    barcode_var = f"89088{int(uid[:6], 16) % 10000000:07d}"

    create_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Organic Wheat Flour",
            "sku": f"FLOUR-{uid.upper()}",
            "barcode": barcode_main,
            "cost_price": "80.00",
            "selling_price": "100.00",
            "mrp": "120.00",
            "gst_rate": 0,
            "hsn_code": "1101",
            "unit": "kg",
            "track_batch": True,
            "batch_number": f"BAT-{uid.upper()}",
            "store_id": store_id,
            "opening_stock": 25,
            "variants": [
                {
                    "variant_name": "5kg Family Pack",
                    "sku": f"FLOUR5K-{uid.upper()}",
                    "barcode": barcode_var,
                    "selling_price": "480.00",
                    "cost_price": "390.00",
                }
            ],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    prod = create_resp.json()

    assert Decimal(str(prod["cost_price"])) == Decimal("80.00")
    assert Decimal(str(prod["gst_rate"])) == Decimal("0.00")
    assert Decimal(str(prod["tax_rate"])) == Decimal("0.00")
    assert Decimal(str(prod["effective_gst_rate"])) == Decimal("0.00")
    assert Decimal(str(prod["available_stock"])) == Decimal("25.0000")
    assert isinstance(prod["variants"], list) and len(prod["variants"]) == 1
    assert prod["variants"][0]["id"] is not None
    assert prod["variants"][0]["variant_name"] == "5kg Family Pack"

    # Verify DB records were created atomically
    db = SessionLocal()
    try:
        db_inv = (
            db.query(Inventory)
            .filter(
                Inventory.tenant_id == env["tenant_id"],
                Inventory.store_id == store_id,
                Inventory.product_id == prod["id"],
            )
            .first()
        )
        assert db_inv is not None and Decimal(str(db_inv.quantity)) == Decimal("25.0000")
        db_batch = (
            db.query(ProductBatch)
            .filter(
                ProductBatch.tenant_id == env["tenant_id"],
                ProductBatch.product_id == prod["id"],
            )
            .first()
        )
        assert db_batch is not None and db_batch.batch_number == f"BAT-{uid.upper()}"
        db_var = (
            db.query(ProductVariant)
            .filter(ProductVariant.product_id == prod["id"])
            .first()
        )
        assert db_var is not None and Decimal(str(db_var.selling_price)) == Decimal("480.00")
    finally:
        db.close()

    # Lookup by ID and barcode with store_id enrichment
    get_resp = client.get(f"/api/v1/products/{prod['id']}?store_id={store_id}", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    assert Decimal(str(get_resp.json()["available_stock"])) == Decimal("25.0000")

    bar_resp = client.get(f"/api/v1/products/barcode/{barcode_main}?store_id={store_id}", headers=headers)
    assert bar_resp.status_code == 200, bar_resp.text
    assert bar_resp.json()["id"] == prod["id"]

    # Update cost_price and gst_rate=0 -> 5
    patch_resp = client.patch(
        f"/api/v1/products/{prod['id']}",
        json={"cost_price": "82.50", "gst_rate": 5},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert Decimal(str(patch_resp.json()["cost_price"])) == Decimal("82.50")
    assert Decimal(str(patch_resp.json()["gst_rate"])) == Decimal("5.00")


def test_invoice_preview_direct_create_cart_and_pos_checkout():
    """Verify product_id/variant_id auto-fetch across /invoices/preview, /billing/preview, /invoices, /billing/cart, and /orders/pos-checkout."""
    env = _create_admin_session("invconn")
    headers = env["headers"]
    store_id = env["store"]["id"]
    uid = env["uid"]
    p_barcode = f"89055{int(uid[:6], 16) % 10000000:07d}"
    v_barcode = f"89066{int(uid[:6], 16) % 10000000:07d}"

    p_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Cotton Kurti",
            "sku": f"KUR-{uid.upper()}",
            "barcode": p_barcode,
            "cost_price": "150.00",
            "selling_price": "200.00",
            "mrp": "299.00",
            "gst_rate": "12.00",
            "hsn_code": "6204",
            "unit": "box",
            "store_id": store_id,
            "opening_stock": 20,
            "variants": [
                {
                    "variant_name": "Size L Blue",
                    "sku": f"KURL-{uid.upper()}",
                    "barcode": v_barcode,
                    "selling_price": "260.00",
                    "cost_price": "190.00",
                }
            ],
        },
        headers=headers,
    )
    assert p_resp.status_code == 201, p_resp.text
    prod = p_resp.json()
    var_id = prod["variants"][0]["id"]

    # 5% GST item for POS checkout check (must not use hardcoded 18%)
    tea_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Assam Leaf Tea",
            "sku": f"ATEA-{uid.upper()}",
            "selling_price": "100.00",
            "cost_price": "70.00",
            "mrp": "120.00",
            "gst_rate": "5.00",
            "hsn_code": "0902",
            "unit": "pack",
            "store_id": store_id,
            "opening_stock": 20,
        },
        headers=headers,
    )
    assert tea_resp.status_code == 201, tea_resp.text
    tea = tea_resp.json()

    # Inactive & expired products must be rejected at invoice/cart time
    db = SessionLocal()
    try:
        inactive_p = Product(
            tenant_id=env["tenant_id"],
            name="Old Inactive Product",
            sku=f"INACT-{uid.upper()}",
            selling_price=Decimal("50.00"),
            mrp=Decimal("60.00"),
            tax_rate=Decimal("5.00"),
            is_active=False,
        )
        expired_p = Product(
            tenant_id=env["tenant_id"],
            name="Expired Milk",
            sku=f"EXP-{uid.upper()}",
            selling_price=Decimal("50.00"),
            mrp=Decimal("60.00"),
            tax_rate=Decimal("0.00"),
            is_active=True,
            expiry_date=date.today() - timedelta(days=2),
        )
        db.add_all([inactive_p, expired_p])
        db.commit()
        inactive_id = inactive_p.id
        expired_id = expired_p.id
    finally:
        db.close()

    # 1. Invoice Preview & Billing Preview auto-fetch variant price, HSN, unit, GST & stock
    preview_payload = {
        "store_id": store_id,
        "same_state": True,
        "discount_amount": "10.00",
        "items": [{"product_id": prod["id"], "variant_id": var_id, "quantity": 2}],
    }
    prev_resp = client.post("/api/v1/invoices/preview", json=preview_payload, headers=headers)
    assert prev_resp.status_code == 200, prev_resp.text
    prev = prev_resp.json()
    assert prev["all_items_in_stock"] is True
    assert Decimal(str(prev["subtotal"])) == Decimal("520.00")  # 260 * 2
    assert Decimal(str(prev["gst_amount"])) == Decimal("62.40")  # 12% of 520
    assert Decimal(str(prev["discount_amount"])) == Decimal("52.00")  # 10% of 520
    p_item = prev["items"][0]
    assert p_item["product_name"] == "Cotton Kurti"
    assert p_item["variant_name"] == "Size L Blue"
    assert p_item["hsn_code"] == "6204"
    assert p_item["unit"] == "box"
    assert Decimal(str(p_item["unit_price"])) == Decimal("260.00")
    assert Decimal(str(p_item["available_stock"])) == Decimal("20.0000")

    b_prev_resp = client.post("/api/v1/billing/preview", json=preview_payload, headers=headers)
    assert b_prev_resp.status_code == 200, b_prev_resp.text
    assert b_prev_resp.json()["grand_total"] == prev["grand_total"]

    # 2. Direct POST /invoices populates enriched InvoiceItem fields + Order.payment_status='paid'
    inv_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "same_state": True,
            "discount_amount": "10.00",
            "items": [{"product_id": prod["id"], "variant_id": var_id, "quantity": 2}],
            "payments": [{"payment_mode": "upi", "amount": prev["grand_total"]}],
        },
        headers=headers,
    )
    assert inv_resp.status_code == 201, inv_resp.text
    inv = inv_resp.json()
    assert len(inv["items"]) == 1
    inv_item = inv["items"][0]
    assert inv_item["product_name"] == "Cotton Kurti"
    assert inv_item["variant_id"] == var_id
    assert inv_item["variant_name"] == "Size L Blue"
    assert inv_item["hsn_code"] == "6204"
    assert inv_item["unit"] == "box"
    assert Decimal(str(inv_item["cgst_amount"])) == Decimal("31.20")
    assert Decimal(str(inv_item["sgst_amount"])) == Decimal("31.20")

    db = SessionLocal()
    try:
        ord_row = db.query(Order).filter(Order.id == inv["order_id"]).first()
        assert ord_row is not None and ord_row.payment_status == "paid"
    finally:
        db.close()

    # 3. Inactive and expired product rejections
    assert client.post(
        "/api/v1/invoices/preview",
        json={"store_id": store_id, "items": [{"product_id": inactive_id, "quantity": 1}]},
        headers=headers,
    ).status_code == 400
    assert client.post(
        "/api/v1/invoices/preview",
        json={"store_id": store_id, "items": [{"product_id": expired_id, "quantity": 1}]},
        headers=headers,
    ).status_code == 400

    # 4. Billing cart variant barcode scan + variant add/update + checkout
    scan_resp = client.post(
        "/api/v1/billing/cart/scan",
        json={"store_id": store_id, "barcode": v_barcode, "quantity": 1},
        headers=headers,
    )
    assert scan_resp.status_code == 200, scan_resp.text
    cart_data = scan_resp.json()
    assert len(cart_data["items"]) == 1
    assert cart_data["items"][0]["variant_id"] == var_id
    assert Decimal(str(cart_data["items"][0]["unit_price"])) == Decimal("260.00")

    checkout_resp = client.post(
        "/api/v1/billing/checkout",
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [{"payment_mode": "cash", "amount": cart_data["grand_total"]}],
        },
        headers=headers,
    )
    assert checkout_resp.status_code == 201, checkout_resp.text
    assert checkout_resp.json()["items"][0]["variant_id"] == var_id

    # 5. POS Checkout honors real product GST (5%, NOT hardcoded 18%)
    pos_resp = client.post(
        "/api/v1/orders/pos-checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": tea["id"], "quantity": 2}],
            "payment": {"payment_method": "cash", "amount": "250.00"},
            "generate_invoice": True,
        },
        headers=headers,
    )
    assert pos_resp.status_code == 201, pos_resp.text
    pos_data = pos_resp.json()
    assert Decimal(str(pos_data["order"]["tax_amount"])) == Decimal("10.00")
    assert Decimal(str(pos_data["invoice"]["cgst_amount"])) == Decimal("5.00")
    assert Decimal(str(pos_data["invoice"]["sgst_amount"])) == Decimal("5.00")
    assert Decimal(str(pos_data["invoice"]["total_amount"])) == Decimal("210.00")
    pos_item = pos_data["invoice"]["items"][0]
    assert pos_item["product_name"] == "Assam Leaf Tea"
    assert pos_item["hsn_code"] == "0902"
    assert pos_item["unit"] == "pack"
    assert Decimal(str(pos_item["cgst_amount"])) == Decimal("5.00")


def test_cross_module_po_inventory_and_storefront_connectivity():
    """Verify PO product auto-fetch, inventory track_batch fallback, and storefront dynamic GST calculation."""
    env = _create_admin_session("xmconn")
    headers = env["headers"]
    store_id = env["store"]["id"]
    uid = env["uid"]

    p_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Wireless Earbuds",
            "sku": f"EAR-{uid.upper()}",
            "cost_price": "500.00",
            "selling_price": "1000.00",
            "mrp": "1499.00",
            "gst_rate": "12.00",
            "hsn_code": "8518",
            "unit": "box",
            "track_batch": True,
            "batch_number": f"EBAT-{uid.upper()}",
        },
        headers=headers,
    )
    assert p_resp.status_code == 201, p_resp.text
    prod = p_resp.json()

    # 1. Stock-in on track_batch=True product without explicit batch_number creates ProductBatch
    in_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": prod["id"], "quantity": 10},
        headers=headers,
    )
    assert in_resp.status_code == 201, in_resp.text

    db = SessionLocal()
    try:
        batches = (
            db.query(ProductBatch)
            .filter(
                ProductBatch.tenant_id == env["tenant_id"],
                ProductBatch.product_id == prod["id"],
            )
            .all()
        )
        assert len(batches) == 1
        assert Decimal(str(batches[0].quantity)) == Decimal("10.0000")

        supplier = Supplier(
            tenant_id=env["tenant_id"],
            name=f"Tech Supplier {uid}",
            phone=f"9911{int(uid[:6], 16) % 1000000:06d}",
            is_active=True,
        )
        customer = Customer(
            tenant_id=env["tenant_id"],
            name="Storefront Buyer",
            phone=f"9822{int(uid[:6], 16) % 1000000:06d}",
            address="Pune MH",
        )
        db.add_all([supplier, customer])
        db.commit()
        supplier_id = supplier.id
        customer_id = customer.id
    finally:
        db.close()

    # 2. Purchase Order omitting unit_cost, tax_rate, hsn_code, unit_of_measure auto-fetches from Product
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier_id,
            "store_id": store_id,
            "items": [{"product_id": prod["id"], "quantity": 4}],
        },
        headers=headers,
    )
    assert po_resp.status_code == 201, po_resp.text
    po = po_resp.json()
    po_item = po["items"][0]
    assert Decimal(str(po_item["unit_cost"])) == Decimal("500.00")
    assert Decimal(str(po_item["tax_rate"])) == Decimal("12.00")
    assert po_item["hsn_code"] == "8518"
    assert po_item["unit_of_measure"] == "box"
    assert Decimal(str(po["subtotal"])) == Decimal("2000.00")
    assert Decimal(str(po["tax_amount"])) == Decimal("240.00")

    # 3. Storefront dynamic GST calculation & stock deduction
    db = SessionLocal()
    try:
        cust = db.query(Customer).filter(Customer.id == customer_id).first()
        sf = StorefrontService(db)
        sf.clear_cart(env["tenant_id"], cust.id)
        cart = sf.add_to_cart(env["tenant_id"], cust.id, prod["id"], quantity=2)
        assert Decimal(str(cart.subtotal)) == Decimal("2000.00")
        assert Decimal(str(cart.tax_amount)) == Decimal("240.00")  # 12% GST instead of hardcoded 5%
        assert Decimal(str(cart.total_amount)) == Decimal("2240.00")

        checkout_res = sf.checkout(
            env["tenant_id"],
            cust,
            StorefrontCheckoutRequest(store_id=store_id, delivery_type="delivery", payment_method="cod"),
        )
        assert Decimal(str(checkout_res.total_amount)) == Decimal("2240.00")

        inv_after = (
            db.query(Inventory)
            .filter(
                Inventory.tenant_id == env["tenant_id"],
                Inventory.store_id == store_id,
                Inventory.product_id == prod["id"],
            )
            .first()
        )
        assert Decimal(str(inv_after.quantity)) == Decimal("8.0000")
    finally:
        db.close()


def test_list_invoices_api_without_required_search_and_filters():
    """Verify GET /api/v1/invoices acts as a proper paginated List Invoices endpoint with optional search/filters."""
    env = _create_admin_session("invlist")
    headers = env["headers"]
    store_id = env["store"]["id"]
    uid = env["uid"]

    # Check OpenAPI summary shows List Invoices (not Search Invoices)
    schema_resp = client.get("/api/v1/openapi.json")
    assert schema_resp.status_code == 200
    get_spec = schema_resp.json()["paths"]["/api/v1/invoices"]["get"]
    assert get_spec["summary"] == "List Invoices"

    # Empty tenant list works without any query parameters (no 422 wall)
    empty_resp = client.get("/api/v1/invoices", headers=headers)
    assert empty_resp.status_code == 200, empty_resp.text
    empty_data = empty_resp.json()
    assert empty_data["items"] == []
    assert empty_data["total"] == 0
    assert empty_data["page"] == 1
    assert empty_data["page_size"] == 20

    # Seed customer + product
    cust_phone = f"9876{int(uid[:6], 16) % 1000000:06d}"
    cust_resp = client.post(
        "/api/v1/customers",
        json={"name": "Aarav Deshmukh", "phone": cust_phone, "email": f"aarav-{uid}@test.com"},
        headers=headers,
    )
    assert cust_resp.status_code == 201, cust_resp.text
    cust_id = cust_resp.json()["id"]

    p_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Basmati Rice 5kg",
            "sku": f"RICE-{uid.upper()}",
            "selling_price": "500.00",
            "cost_price": "400.00",
            "mrp": "550.00",
            "gst_rate": "5.00",
            "store_id": store_id,
            "opening_stock": 50,
        },
        headers=headers,
    )
    assert p_resp.status_code == 201, p_resp.text
    prod_id = p_resp.json()["id"]

    # Create 1 paid invoice (linked to customer) and 1 unpaid/issued invoice (no Payment row)
    paid_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "customer_id": cust_id,
            "same_state": True,
            "items": [{"product_id": prod_id, "quantity": 1}],
            "payments": [{"payment_mode": "upi", "amount": "525.00"}],
        },
        headers=headers,
    )
    assert paid_resp.status_code == 201, paid_resp.text
    paid_inv = paid_resp.json()

    unpaid_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "same_state": True,
            "items": [{"product_id": prod_id, "quantity": 1}],
            "payments": [],
        },
        headers=headers,
    )
    assert unpaid_resp.status_code == 201, unpaid_resp.text
    unpaid_inv = unpaid_resp.json()

    # 1. Default list with no params returns both invoices and accurate counts
    list_all = client.get("/api/v1/invoices", headers=headers)
    assert list_all.status_code == 200, list_all.text
    body = list_all.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["counts"]["total"] == 2
    assert body["counts"]["paid"] == 1
    assert body["counts"]["unpaid"] == 1

    # 2. Pagination check
    page_res = client.get("/api/v1/invoices?page=1&page_size=1", headers=headers)
    assert page_res.status_code == 200
    assert len(page_res.json()["items"]) == 1
    assert page_res.json()["total"] == 2
    assert page_res.json()["total_pages"] == 2

    # 3. Unified search by customer name matches paid invoice
    search_cust = client.get("/api/v1/invoices?search=Deshmukh", headers=headers)
    assert search_cust.status_code == 200
    assert [x["id"] for x in search_cust.json()["items"]] == [paid_inv["id"]]

    # 4. Unified search by invoice number matches unpaid invoice
    search_inv = client.get(f"/api/v1/invoices?search={unpaid_inv['invoice_number']}", headers=headers)
    assert search_inv.status_code == 200
    assert [x["id"] for x in search_inv.json()["items"]] == [unpaid_inv["id"]]

    # 5. payment_status=unpaid returns unpaid invoice even without Payment rows
    unpaid_list = client.get("/api/v1/invoices?payment_status=unpaid", headers=headers)
    assert unpaid_list.status_code == 200
    assert [x["id"] for x in unpaid_list.json()["items"]] == [unpaid_inv["id"]]

    # 6. customer_id & status filters
    cust_filtered = client.get(f"/api/v1/invoices?customer_id={cust_id}&status=paid", headers=headers)
    assert cust_filtered.status_code == 200
    assert [x["id"] for x in cust_filtered.json()["items"]] == [paid_inv["id"]]


def test_product_create_and_update_multipart_form_data():
    """Verify multipart/form-data Swagger schema and runtime upload/variants/opening_stock/cost_price on /products."""
    env = _create_admin_session("prdform")
    headers = env["headers"]
    store_id = env["store"]["id"]
    uid = env["uid"]

    # 1. Verify OpenAPI multipart/form-data schema is Swagger-safe and clean (no pre-filled defaults/examples)
    openapi_resp = client.get("/api/v1/openapi.json")
    assert openapi_resp.status_code == 200
    spec = openapi_resp.json()
    form_schema = spec["paths"]["/api/v1/products"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert form_schema["required"] == ["name", "sku", "selling_price"]
    form_props = form_schema["properties"]
    assert form_props["variants"]["type"] == "string"
    assert form_props["gst_rate"]["enum"] == [0, 5, 12, 18, 28]
    assert form_props["stock_status"]["enum"] == ["in_stock", "out_of_stock", "low_stock"]
    assert "price" not in form_props
    assert all("default" not in prop and "example" not in prop for prop in form_props.values())

    # 2. Invalid variants JSON returns clean 422
    bad_form_resp = client.post(
        "/api/v1/products",
        data={
            "name": "Sunflower Oil 1L",
            "sku": f"OILBAD-{uid.upper()}",
            "selling_price": "150.00",
            "variants": "[object Object]",
        },
        headers=headers,
    )
    assert bad_form_resp.status_code == 422, bad_form_resp.text

    # 3. Full multipart/form-data create with binary image, variants JSON string, cost_price, gst_rate=0, opening_stock
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    variants_json = json.dumps([
        {
            "variant_name": "500ml Bottle",
            "sku": f"OIL500-{uid.upper()}",
            "selling_price": 80.00,
            "cost_price": 62.00,
        }
    ])
    create_resp = client.post(
        "/api/v1/products",
        data={
            "name": "Fortune Sunflower Oil 1L",
            "sku": f"OIL-{uid.upper()}",
            "selling_price": "150.00",
            "cost_price": "120.00",
            "mrp": "165.00",
            "store_id": str(store_id),
            "opening_stock": "15",
            "variants": variants_json,
            "unit": "ltr",
            "hsn_code": "1512",
            "gst_rate": "0",
            "min_stock_alert": "10",
            "stock_status": "in_stock",
            "is_active": "true",
            "track_batch": "false",
            "track_expiry": "false",
        },
        files={"image": ("oil.png", io.BytesIO(png_bytes), "image/png")},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    prod = create_resp.json()
    assert Decimal(str(prod["cost_price"])) == Decimal("120.00")
    assert Decimal(str(prod["gst_rate"])) == Decimal("0.00")
    assert Decimal(str(prod["effective_gst_rate"])) == Decimal("0.00")
    assert Decimal(str(prod["available_stock"])) == Decimal("15.0000")
    assert prod["image_url"] is not None and prod["image_url"].startswith("/uploads/products/")
    assert len(prod["images"]) == 1
    assert isinstance(prod["variants"], list) and len(prod["variants"]) == 1
    assert prod["variants"][0]["id"] is not None
    assert prod["variants"][0]["variant_name"] == "500ml Bottle"

    # 4. PATCH via multipart/form-data with tax_rate alias + new photo
    patch_resp = client.patch(
        f"/api/v1/products/{prod['id']}",
        data={
            "cost_price": "125.00",
            "tax_rate": "5",
        },
        files={"image": ("oil_v2.png", io.BytesIO(png_bytes), "image/png")},
        headers=headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()
    assert Decimal(str(updated["cost_price"])) == Decimal("125.00")
    assert Decimal(str(updated["gst_rate"])) == Decimal("5.00")
    assert updated["image_url"] is not None and updated["image_url"] != prod["image_url"]
