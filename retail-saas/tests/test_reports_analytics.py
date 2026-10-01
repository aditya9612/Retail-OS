from datetime import date, datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.refund import Refund
from app.models.role import Role
from app.models.store import Store
from app.models.store_expense import StoreExpense
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def reports_fixture():
    db = SessionLocal()
    slug = f"rep-{uuid.uuid4().hex[:8]}"

    tenant = Tenant(name=f"Report Tenant {slug}", domain=slug, is_active=True)
    db.add(tenant)
    db.flush()

    role_owner = Role(tenant_id=tenant.id, name="owner", permissions=["*"])
    role_manager = Role(
        tenant_id=tenant.id,
        name="manager",
        permissions=["reports:read", "billing:read", "inventory:read"],
    )
    db.add_all([role_owner, role_manager])
    db.flush()

    # Stores
    store1 = Store(tenant_id=tenant.id, name="Store 1", code=f"S1-{slug[:4]}")
    store2 = Store(tenant_id=tenant.id, name="Store 2", code=f"S2-{slug[:4]}")
    db.add_all([store1, store2])
    db.flush()

    # Users
    owner_user = User(
        tenant_id=tenant.id,
        role_id=role_owner.id,
        email=f"owner-{slug}@test.com",
        password_hash=get_password_hash("password123"),
        full_name="Owner User",
        is_active=True,
        is_deleted=False,
        store_id=None,
    )
    manager_user = User(
        tenant_id=tenant.id,
        role_id=role_manager.id,
        email=f"manager-{slug}@test.com",
        password_hash=get_password_hash("password123"),
        full_name="Manager User",
        is_active=True,
        is_deleted=False,
        store_id=store1.id,  # Assigned strictly to Store 1
    )
    db.add_all([owner_user, manager_user])
    db.flush()

    # Products: cost_price mapped column verified
    p1 = Product(
        tenant_id=tenant.id,
        name="Product Alpha",
        sku=f"SKU-A-{slug[:4]}",
        selling_price=Decimal("500.00"),
        cost_price=Decimal("300.00"),
        gst_rate=Decimal("18.00"),
        min_stock_alert=5,
        is_active=True,
    )
    p2 = Product(
        tenant_id=tenant.id,
        name="Product Beta",
        sku=f"SKU-B-{slug[:4]}",
        selling_price=Decimal("200.00"),
        cost_price=Decimal("100.00"),
        gst_rate=Decimal("12.00"),
        min_stock_alert=10,
        is_active=True,
    )
    db.add_all([p1, p2])
    db.flush()

    # Inventory
    inv1 = Inventory(
        tenant_id=tenant.id,
        store_id=store1.id,
        product_id=p1.id,
        quantity=20,
        min_stock_level=5,
        reorder_point=8,
    )
    inv2 = Inventory(
        tenant_id=tenant.id,
        store_id=store1.id,
        product_id=p2.id,
        quantity=3,  # Low stock: 3 <= min_stock_level (10), deficit = 7
        min_stock_level=10,
        reorder_point=12,
    )
    db.add_all([inv1, inv2])
    db.flush()

    # Customers: 1 active, 1 inactive; segment testing
    c1 = Customer(
        tenant_id=tenant.id,
        name="Alice Active",
        email=f"alice-{slug}@test.com",
        phone=f"98765{slug[:5]}",
        status="active",
        segment="regular",
        loyalty_points=120,
        total_spend=1500,
    )
    c2 = Customer(
        tenant_id=tenant.id,
        name="Bob Inactive",
        email=f"bob-{slug}@test.com",
        phone=f"98764{slug[:5]}",
        status="inactive",
        segment="new",
        loyalty_points=0,
        total_spend=0,
    )
    db.add_all([c1, c2])
    db.flush()

    # Today's date
    today = date.today()
    now = datetime.combine(today, datetime.min.time()) + timedelta(hours=10)

    # Order 1 in Store 1
    o1 = Order(
        tenant_id=tenant.id,
        store_id=store1.id,
        customer_id=c1.id,
        order_number=f"ORD-1-{slug[:4]}",
        status="confirmed",
        subtotal=Decimal("1000.00"),
        discount_amount=Decimal("100.00"),
        tax_amount=Decimal("162.00"),
        total_amount=Decimal("1062.00"),
        payment_status="completed",
        created_at=now,
    )
    db.add(o1)
    db.flush()

    item1 = OrderItem(
        order_id=o1.id,
        product_id=p1.id,
        quantity=2,
        unit_price=Decimal("500.00"),
        discount_amount=Decimal("100.00"),
        tax_amount=Decimal("162.00"),
        total_amount=Decimal("1062.00"),
        cgst_amount=Decimal("81.00"),
        sgst_amount=Decimal("81.00"),
        igst_amount=Decimal("0.00"),
    )
    db.add(item1)
    db.flush()

    # Invoice 1 for Order 1
    invc1 = Invoice(
        tenant_id=tenant.id,
        order_id=o1.id,
        invoice_number=f"INV-1-{slug[:4]}",
        subtotal=Decimal("1000.00"),
        discount_amount=Decimal("100.00"),
        tax_amount=Decimal("162.00"),
        total_amount=Decimal("1062.00"),
        cgst_amount=Decimal("81.00"),
        sgst_amount=Decimal("81.00"),
        igst_amount=Decimal("0.00"),
        created_at=now,
    )
    db.add(invc1)
    db.flush()

    inv_item1 = InvoiceItem(
        invoice_id=invc1.id,
        product_id=p1.id,
        quantity=Decimal("2.00"),
        unit_price=Decimal("500.00"),
        discount_amount=Decimal("100.00"),
        gst_rate=Decimal("18.00"),
        gst_amount=Decimal("162.00"),
        total_amount=Decimal("1062.00"),
    )
    db.add(inv_item1)
    db.flush()

    # Payment for Order 1: Cash
    pay1 = Payment(
        tenant_id=tenant.id,
        order_id=o1.id,
        payment_method="cash",
        amount=Decimal("1062.00"),
        status="completed",
        created_at=now,
    )
    db.add(pay1)
    db.flush()

    # Order 2 in Store 2
    o2 = Order(
        tenant_id=tenant.id,
        store_id=store2.id,
        customer_id=c1.id,
        order_number=f"ORD-2-{slug[:4]}",
        status="confirmed",
        subtotal=Decimal("400.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("48.00"),
        total_amount=Decimal("448.00"),
        payment_status="completed",
        created_at=now,
    )
    db.add(o2)
    db.flush()

    item2 = OrderItem(
        order_id=o2.id,
        product_id=p2.id,
        quantity=2,
        unit_price=Decimal("200.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("48.00"),
        total_amount=Decimal("448.00"),
        cgst_amount=Decimal("24.00"),
        sgst_amount=Decimal("24.00"),
        igst_amount=Decimal("0.00"),
    )
    db.add(item2)
    db.flush()

    invc2 = Invoice(
        tenant_id=tenant.id,
        order_id=o2.id,
        invoice_number=f"INV-2-{slug[:4]}",
        subtotal=Decimal("400.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("48.00"),
        total_amount=Decimal("448.00"),
        cgst_amount=Decimal("24.00"),
        sgst_amount=Decimal("24.00"),
        igst_amount=Decimal("0.00"),
        created_at=now,
    )
    db.add(invc2)
    db.flush()

    inv_item2 = InvoiceItem(
        invoice_id=invc2.id,
        product_id=p2.id,
        quantity=Decimal("2.00"),
        unit_price=Decimal("200.00"),
        discount_amount=Decimal("0.00"),
        gst_rate=Decimal("12.00"),
        gst_amount=Decimal("48.00"),
        total_amount=Decimal("448.00"),
    )
    db.add(inv_item2)
    db.flush()

    pay2 = Payment(
        tenant_id=tenant.id,
        order_id=o2.id,
        payment_method="upi",
        amount=Decimal("448.00"),
        status="completed",
        created_at=now,
    )
    db.add(pay2)
    db.flush()

    # Refund for Store 1 Order (approved)
    ref1 = Refund(
        tenant_id=tenant.id,
        invoice_id=invc1.id,
        refund_amount=Decimal("62.00"),
        refund_method="cash",
        status="approved",
        created_at=now,
    )
    db.add(ref1)
    db.flush()

    # Store Expense: store_expenses has NO tenant_id; scopes via store_id -> Store.tenant_id
    exp1 = StoreExpense(
        store_id=store1.id,
        amount=Decimal("150.00"),
        category="utilities",
        description="Electricity bill",
        expense_date=today,
        status="active",
    )
    db.add(exp1)
    db.commit()

    # Auth headers
    owner_token = create_access_token({"sub": str(owner_user.id), "tenant_id": tenant.id, "role": "owner"})
    manager_token = create_access_token({"sub": str(manager_user.id), "tenant_id": tenant.id, "role": "manager"})

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    data = {
        "tenant": tenant,
        "store1": store1,
        "store2": store2,
        "product1": p1,
        "product2": p2,
        "customer1": c1,
        "customer2": c2,
        "owner_headers": owner_headers,
        "manager_headers": manager_headers,
        "today": today,
    }
    yield data
    db.close()


# ============================================================================
# 1. SALES REPORTS TESTS
# ============================================================================

def test_daily_sales_store_filter(reports_fixture):
    headers = reports_fixture["owner_headers"]
    s1_id = reports_fixture["store1"].id
    today = str(reports_fixture["today"])

    # Tenant-wide (both stores): order_count = 2 (1062 + 448 = 1510)
    resp_all = client.get(f"/api/v1/reports/sales/daily?target_date={today}", headers=headers)
    assert resp_all.status_code == 200, resp_all.text
    data_all = resp_all.json()
    assert data_all["order_count"] == 2
    assert Decimal(str(data_all["total_sales"])) == Decimal("1510.00")
    assert Decimal(str(data_all["refund_amount"])) == Decimal("62.00")
    assert Decimal(str(data_all["net_sales"])) == Decimal("1448.00")
    assert "cash" in data_all["payment_methods"]
    assert "upi" in data_all["payment_methods"]

    # Store 1 only: order_count = 1 (total_sales = 1062.00)
    resp_s1 = client.get(
        f"/api/v1/reports/sales/daily?target_date={today}&store_id={s1_id}",
        headers=headers,
    )
    assert resp_s1.status_code == 200
    data_s1 = resp_s1.json()
    assert data_s1["order_count"] == 1
    assert Decimal(str(data_s1["total_sales"])) == Decimal("1062.00")
    assert Decimal(str(data_s1["refund_amount"])) == Decimal("62.00")
    assert Decimal(str(data_s1["net_sales"])) == Decimal("1000.00")
    assert "cash" in data_s1["payment_methods"]
    assert "upi" not in data_s1["payment_methods"]


def test_daily_sales_aov_calculation(reports_fixture):
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])

    resp = client.get(f"/api/v1/reports/sales/daily?target_date={today}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_count"] == 2
    total_sales = Decimal(str(data["total_sales"]))
    aov = Decimal(str(data["average_order_value"]))
    assert aov == (total_sales / 2).quantize(Decimal("0.01"))


def test_daily_sales_zero_data(reports_fixture):
    headers = reports_fixture["owner_headers"]
    past_date = str(date.today() - timedelta(days=30))

    resp = client.get(f"/api/v1/reports/sales/daily?target_date={past_date}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_count"] == 0
    assert Decimal(str(data["total_sales"])) == Decimal("0.00")
    assert Decimal(str(data["net_sales"])) == Decimal("0.00")
    assert Decimal(str(data["average_order_value"])) == Decimal("0.00")
    assert data["payment_methods"] == {}


def test_yearly_sales_breakdown(reports_fixture):
    headers = reports_fixture["owner_headers"]
    year = reports_fixture["today"].year

    resp = client.get(f"/api/v1/reports/sales/yearly?year={year}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] == year
    assert len(data["monthly_breakdown"]) == 12
    total_orders = sum(m["order_count"] for m in data["monthly_breakdown"])
    assert total_orders == data["total_orders"]
    total_sales = sum(Decimal(str(m["total_sales"])) for m in data["monthly_breakdown"])
    assert total_sales == Decimal(str(data["total_sales"]))


# ============================================================================
# 2. GST REPORTS TESTS
# ============================================================================

def test_gst_sales_report(reports_fixture):
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])

    resp = client.get(f"/api/v1/reports/gst/sales?start_date={today}&end_date={today}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["invoice_count"] == 2
    assert Decimal(str(data["taxable_amount"])) == Decimal("1300.00")  # (1000 - 100) + 400
    assert Decimal(str(data["cgst_amount"])) == Decimal("105.00")  # 81 + 24
    assert Decimal(str(data["sgst_amount"])) == Decimal("105.00")  # 81 + 24
    assert Decimal(str(data["total_tax"])) == Decimal("210.00")  # 162 + 48
    assert any("18" in k for k in data["rate_breakdown"])


def test_gst_summary_report(reports_fixture):
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])

    resp = client.get(f"/api/v1/reports/gst/summary?start_date={today}&end_date={today}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["invoice_count"] == 2
    assert Decimal(str(data["total_output_tax"])) == Decimal("210.00")
    assert Decimal(str(data["input_tax_credit"])) == Decimal("0.00")
    assert Decimal(str(data["net_tax_liability"])) == Decimal("210.00")
    assert "ITC" in data["note"]


def test_gst_store_filter(reports_fixture):
    headers = reports_fixture["owner_headers"]
    s2_id = reports_fixture["store2"].id
    today = str(reports_fixture["today"])

    resp = client.get(
        f"/api/v1/reports/gst/sales?start_date={today}&end_date={today}&store_id={s2_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["invoice_count"] == 1
    assert Decimal(str(data["total_tax"])) == Decimal("48.00")


# ============================================================================
# 3. INVENTORY REPORTS TESTS
# ============================================================================

def test_current_stock_report(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/inventory/current-stock", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] >= 2
    assert data["total_quantity"] >= 23
    statuses = [item["stock_status"] for item in data["items"]]
    assert "in_stock" in statuses
    assert "low_stock" in statuses


def test_low_stock_report(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/inventory/low-stock", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_low_stock_products"] >= 1
    low_item = next(it for it in data["items"] if it["quantity"] == 3)
    assert low_item["deficit"] == 7  # min_stock 10 - qty 3 = 7


def test_inventory_valuation_report(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/inventory/valuation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    # inv1: 20 * 300.00 = 6000.00 cost, 20 * 500.00 = 10000.00 retail
    # inv2: 3 * 100.00 = 300.00 cost, 3 * 200.00 = 600.00 retail
    # Total cost = 6300.00, retail = 10600.00
    assert Decimal(str(data["cost_valuation"])) == Decimal("6300.00")
    assert Decimal(str(data["retail_valuation"])) == Decimal("10600.00")
    assert "data_limitation_note" in data


# ============================================================================
# 4. PRODUCT ANALYTICS TESTS
# ============================================================================

def test_top_selling_products(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/products/top-selling?limit=5", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["products"]) >= 2
    # Verify sorted desc by quantity sold
    qtys = [p["quantity_sold"] for p in data["products"]]
    assert qtys == sorted(qtys, reverse=True)


def test_slow_moving_products_explicit_threshold(reports_fixture):
    headers = reports_fixture["owner_headers"]

    # Explicit threshold = 5; both products sold 2 units, so both <= 5
    resp = client.get("/api/v1/reports/products/slow-moving?threshold=5", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["threshold"] == 5
    for p in data["products"]:
        assert p["quantity_sold"] <= 5


def test_slow_moving_products_requires_threshold(reports_fixture):
    headers = reports_fixture["owner_headers"]

    # Omitting threshold must be rejected (caller-provided threshold is mandatory)
    resp = client.get("/api/v1/reports/products/slow-moving", headers=headers)
    assert resp.status_code == 422


def test_product_profitability(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/products/profitability", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(str(data["total_revenue"])) == Decimal("1510.00")
    # Product 1: 2 * 300 = 600 cost, rev 1062 => profit 462
    # Product 2: 2 * 100 = 200 cost, rev 448 => profit 248
    # Total cost = 800.00, profit = 710.00
    assert Decimal(str(data["total_estimated_cost"])) == Decimal("800.00")
    assert Decimal(str(data["total_estimated_profit"])) == Decimal("710.00")
    assert "data_limitation_note" in data


# ============================================================================
# 5. CUSTOMER ANALYTICS TESTS
# ============================================================================

def test_customer_overview(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/customers/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_customers"] == 2
    assert data["active_customers"] == 1
    assert data["inactive_customers"] == 1
    assert data["total_loyalty_points"] == 120
    assert Decimal(str(data["total_spend_all_customers"])) == Decimal("1500.00")


def test_customer_retention_authoritative_status(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/customers/retention", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_customers"] == 2
    assert data["active_customers"] == 1
    assert data["repeat_customers"] == 1  # Alice has 2 orders
    assert data["repeat_purchase_rate"] == 50.0  # 1 / 2 * 100
    assert data["retention_rate"] == 50.0  # 1 / 2 * 100 (active / total)


def test_customer_lifetime_value(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/customers/lifetime-value?limit=5", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["top_customers"]) >= 1
    assert data["top_customers"][0]["name"] == "Alice Active"
    assert Decimal(str(data["top_customers"][0]["total_spend"])) == Decimal("1500.00")


def test_customer_segments(reports_fixture):
    headers = reports_fixture["owner_headers"]

    resp = client.get("/api/v1/reports/customers/segments", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    counts = data["segment_counts"]
    assert counts.get("regular") == 1
    assert counts.get("new") == 1
    assert data["total_categorized"] == 2


# ============================================================================
# 6. PROFIT & LOSS TESTS
# ============================================================================

def test_profit_loss_store_expense_join(reports_fixture):
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])

    resp = client.get(f"/api/v1/reports/profit-loss?start_date={today}&end_date={today}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Operating expenses = 150.00
    assert Decimal(str(data["operating_expenses"])) == Decimal("150.00")
    # Gross sales = 1400.00, discounts = 100.00, tax = 210.00, invoiced_revenue = 1510.00
    assert Decimal(str(data["gross_sales"])) == Decimal("1400.00")
    assert Decimal(str(data["discounts"])) == Decimal("100.00")
    assert Decimal(str(data["net_revenue_tax_exclusive"])) == Decimal("1300.00")
    assert Decimal(str(data["invoiced_revenue"])) == Decimal("1510.00")
    assert Decimal(str(data["refund_amount"])) == Decimal("62.00")
    # COGS = 800.00
    assert Decimal(str(data["cogs"])) == Decimal("800.00")
    # Gross profit = net_revenue_tax_exclusive (1300) - cogs (800) = 500.00
    assert Decimal(str(data["gross_profit"])) == Decimal("500.00")
    # Net profit = gross_profit (500) - operating_expenses (150) - refund_amount (62) = 288.00
    assert Decimal(str(data["net_profit"])) == Decimal("288.00")


def test_profit_loss_zero_data(reports_fixture):
    headers = reports_fixture["owner_headers"]
    past = str(date.today() - timedelta(days=60))

    resp = client.get(f"/api/v1/reports/profit-loss?start_date={past}&end_date={past}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(str(data["gross_sales"])) == Decimal("0.00")
    assert Decimal(str(data["invoiced_revenue"])) == Decimal("0.00")
    assert Decimal(str(data["cogs"])) == Decimal("0.00")
    assert Decimal(str(data["operating_expenses"])) == Decimal("0.00")
    assert Decimal(str(data["net_profit"])) == Decimal("0.00")


def test_profit_loss_historical_cogs_uses_current_cost(reports_fixture):
    """
    CRITICAL HISTORICAL COGS LIMITATION TEST:
    Verifies that current Product.cost_price is used because historical
    order-level unit cost snapshots do not exist in schema.
    """
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])
    db = SessionLocal()

    try:
        # Check initial COGS (Product 1 cost=300 * 2 + Product 2 cost=100 * 2 = 800.00)
        resp1 = client.get(f"/api/v1/reports/profit-loss?start_date={today}&end_date={today}", headers=headers)
        assert resp1.status_code == 200
        assert Decimal(str(resp1.json()["cogs"])) == Decimal("800.00")

        # Mutate current Product 1 cost_price from 300.00 to 450.00
        p1 = db.query(Product).filter(Product.id == reports_fixture["product1"].id).first()
        p1.cost_price = Decimal("450.00")
        db.commit()

        # Re-query: COGS should now be 450 * 2 + 100 * 2 = 1100.00
        resp2 = client.get(f"/api/v1/reports/profit-loss?start_date={today}&end_date={today}", headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert Decimal(str(data2["cogs"])) == Decimal("1100.00")
        assert "cogs_data_limitation" in data2
    finally:
        # Revert cost_price back
        p1 = db.query(Product).filter(Product.id == reports_fixture["product1"].id).first()
        p1.cost_price = Decimal("300.00")
        db.commit()
        db.close()


# ============================================================================
# 7. EXPORT TESTS (CSV, EXCEL, PDF)
# ============================================================================

def test_export_csv(reports_fixture):
    headers = reports_fixture["owner_headers"]
    body = {
        "report_type": "sales_daily",
        "format": "csv",
        "target_date": str(reports_fixture["today"]),
    }
    resp = client.post("/api/v1/reports/export", json=body, headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert "Gross Sales" in resp.text


def test_export_excel(reports_fixture):
    headers = reports_fixture["owner_headers"]
    body = {
        "report_type": "profit_loss",
        "format": "excel",
        "start_date": str(reports_fixture["today"]),
        "end_date": str(reports_fixture["today"]),
    }
    resp = client.post("/api/v1/reports/export", json=body, headers=headers)
    assert resp.status_code == 200
    assert "spreadsheetml.sheet" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert len(resp.content) > 100


def test_export_pdf(reports_fixture):
    headers = reports_fixture["owner_headers"]
    body = {
        "report_type": "gst_sales",
        "format": "pdf",
        "start_date": str(reports_fixture["today"]),
        "end_date": str(reports_fixture["today"]),
    }
    resp = client.post("/api/v1/reports/export", json=body, headers=headers)
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


# ============================================================================
# 8. SECURITY & TENANT ISOLATION TESTS
# ============================================================================

def test_tenant_isolation(reports_fixture):
    db = SessionLocal()
    slug_b = f"repb-{uuid.uuid4().hex[:8]}"
    tenant_b = Tenant(name=f"Tenant B {slug_b}", domain=slug_b, is_active=True)
    db.add(tenant_b)
    db.flush()

    role_b = Role(tenant_id=tenant_b.id, name="owner", permissions=["*"])
    db.add(role_b)
    db.flush()

    user_b = User(
        tenant_id=tenant_b.id,
        role_id=role_b.id,
        email=f"owner-{slug_b}@test.com",
        password_hash=get_password_hash("password123"),
        full_name="Tenant B Owner",
        is_active=True,
        is_deleted=False,
    )
    db.add(user_b)
    db.commit()

    token_b = create_access_token({"sub": str(user_b.id), "tenant_id": tenant_b.id, "role": "owner"})
    headers_b = {"Authorization": f"Bearer {token_b}"}
    today = str(reports_fixture["today"])

    # Tenant B queries daily sales: should see 0 orders, no leakage from Tenant A
    resp = client.get(f"/api/v1/reports/sales/daily?target_date={today}", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["order_count"] == 0
    assert Decimal(str(resp.json()["total_sales"])) == Decimal("0.00")
    db.close()


def test_store_manager_isolation(reports_fixture):
    manager_headers = reports_fixture["manager_headers"]
    s1_id = reports_fixture["store1"].id
    s2_id = reports_fixture["store2"].id
    today = str(reports_fixture["today"])

    # 1. Store Manager requests Store 2 (foreign to assigned Store 1) => 403 Forbidden
    resp_foreign = client.get(
        f"/api/v1/reports/sales/daily?target_date={today}&store_id={s2_id}",
        headers=manager_headers,
    )
    assert resp_foreign.status_code == 403

    # 2. Store Manager omits store_id => forced to Store 1
    resp_omitted = client.get(
        f"/api/v1/reports/sales/daily?target_date={today}",
        headers=manager_headers,
    )
    assert resp_omitted.status_code == 200
    assert resp_omitted.json()["store_id"] == s1_id
    assert resp_omitted.json()["order_count"] == 1


def test_tenant_owner_invalid_store_404(reports_fixture):
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])

    resp = client.get(
        f"/api/v1/reports/sales/daily?target_date={today}&store_id=999999",
        headers=headers,
    )
    assert resp.status_code == 404


def test_invalid_date_range_400(reports_fixture):
    headers = reports_fixture["owner_headers"]

    # start_date > end_date returns 400 Bad Request
    resp = client.get(
        "/api/v1/reports/gst/sales?start_date=2026-12-31&end_date=2026-01-01",
        headers=headers,
    )
    assert resp.status_code == 400
    assert "start_date must be before or equal to end_date" in resp.json()["detail"]


# ============================================================================
# 9. LEGACY ROUTE DELEGATION TESTS
# ============================================================================

def test_legacy_route_delegates(reports_fixture):
    headers = reports_fixture["owner_headers"]
    today = str(reports_fixture["today"])
    year = reports_fixture["today"].year
    month = reports_fixture["today"].month

    # GET /api/v1/reports/daily-sales
    r_daily = client.get(f"/api/v1/reports/daily-sales?target_date={today}", headers=headers)
    assert r_daily.status_code == 200
    assert r_daily.json()["order_count"] == 2

    # GET /api/v1/reports/monthly-sales
    r_monthly = client.get(f"/api/v1/reports/monthly-sales?year={year}&month={month}", headers=headers)
    assert r_monthly.status_code == 200
    assert r_monthly.json()["order_count"] == 2

    # GET /api/v1/reports/gst
    r_gst = client.get(f"/api/v1/reports/gst?start_date={today}&end_date={today}", headers=headers)
    assert r_gst.status_code == 200
    assert r_gst.json()["invoice_count"] == 2
