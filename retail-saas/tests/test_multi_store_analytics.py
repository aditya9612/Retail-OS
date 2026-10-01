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
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.refund import Refund
from app.models.role import Role
from app.models.saas_billing import SaaSSubscription
from app.models.store import Store
from app.models.store_expense import StoreExpense
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def multi_store_fixture():
    db = SessionLocal()
    slug_a = f"msa-{uuid.uuid4().hex[:8]}"
    slug_b = f"msb-{uuid.uuid4().hex[:8]}"

    # Tenant A
    tenant_a = Tenant(name=f"Tenant A {slug_a}", domain=slug_a, is_active=True)
    tenant_b = Tenant(name=f"Tenant B {slug_b}", domain=slug_b, is_active=True)
    db.add_all([tenant_a, tenant_b])
    db.flush()

    # Subscriptions
    sub_a = SaaSSubscription(
        tenant_id=tenant_a.id,
        plan_id=1,
        status="active",
        billing_interval="monthly",
        unit_price=Decimal("1000.00"),
        currency="INR",
        start_date=datetime.utcnow() - timedelta(days=30),
        current_period_start=datetime.utcnow() - timedelta(days=5),
        current_period_end=datetime.utcnow() + timedelta(days=25),
    )
    db.add(sub_a)
    db.flush()
    tenant_a.current_subscription_id = sub_a.id

    # Roles for Tenant A
    role_owner_a = Role(tenant_id=tenant_a.id, name="owner", permissions=["*"])
    role_manager_a = Role(
        tenant_id=tenant_a.id,
        name="manager",
        permissions=["reports:read", "stores:read"],
    )
    role_cashier_a = Role(
        tenant_id=tenant_a.id,
        name="cashier",
        permissions=["orders:read"],  # Missing reports:read and stores:read
    )
    role_owner_b = Role(tenant_id=tenant_b.id, name="owner", permissions=["*"])
    db.add_all([role_owner_a, role_manager_a, role_cashier_a, role_owner_b])
    db.flush()

    # Stores for Tenant A (3 stores: S1, S2, S3_empty)
    store_a1 = Store(tenant_id=tenant_a.id, name="Downtown Flagship", code=f"DT-{slug_a[:4]}", city="Pune", is_main=True, is_active=True)
    store_a2 = Store(tenant_id=tenant_a.id, name="Suburban Branch", code=f"SB-{slug_a[:4]}", city="Mumbai", is_main=False, is_active=True)
    store_a3 = Store(tenant_id=tenant_a.id, name="Zero Activity Store", code=f"ZA-{slug_a[:4]}", city="Nagpur", is_main=False, is_active=True)

    # Store for Tenant B
    store_b1 = Store(tenant_id=tenant_b.id, name="Tenant B Store", code=f"TB-{slug_b[:4]}", city="Delhi", is_main=True, is_active=True)

    db.add_all([store_a1, store_a2, store_a3, store_b1])
    db.flush()

    # Users
    user_owner_a = User(
        tenant_id=tenant_a.id,
        role_id=role_owner_a.id,
        email=f"owner-{slug_a}@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Tenant A Owner",
        is_active=True,
        is_deleted=False,
        store_id=None,
    )
    user_manager_s1 = User(
        tenant_id=tenant_a.id,
        role_id=role_manager_a.id,
        email=f"mgr-{slug_a}@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Store 1 Manager",
        is_active=True,
        is_deleted=False,
        store_id=store_a1.id,
    )
    user_cashier_a = User(
        tenant_id=tenant_a.id,
        role_id=role_cashier_a.id,
        email=f"cashier-{slug_a}@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Cashier User",
        is_active=True,
        is_deleted=False,
        store_id=store_a1.id,
    )
    user_owner_b = User(
        tenant_id=tenant_b.id,
        role_id=role_owner_b.id,
        email=f"owner-{slug_b}@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Tenant B Owner",
        is_active=True,
        is_deleted=False,
        store_id=None,
    )
    db.add_all([user_owner_a, user_manager_s1, user_cashier_a, user_owner_b])
    db.flush()

    # Products for Tenant A
    prod1 = Product(
        tenant_id=tenant_a.id,
        name="Wireless Mouse",
        sku=f"WM-{slug_a[:4]}",
        selling_price=Decimal("1000.00"),
        cost_price=Decimal("600.00"),
        min_stock_alert=5,
        is_active=True,
    )
    prod2 = Product(
        tenant_id=tenant_a.id,
        name="Mechanical Keyboard",
        sku=f"KB-{slug_a[:4]}",
        selling_price=Decimal("3000.00"),
        cost_price=Decimal("1800.00"),
        min_stock_alert=10,
        is_active=True,
    )
    # Product for Tenant B
    prod_b = Product(
        tenant_id=tenant_b.id,
        name="Tenant B Widget",
        sku=f"TBW-{slug_b[:4]}",
        selling_price=Decimal("500.00"),
        cost_price=Decimal("250.00"),
        min_stock_alert=2,
        is_active=True,
    )
    db.add_all([prod1, prod2, prod_b])
    db.flush()

    # Inventory
    inv_s1_p1 = Inventory(tenant_id=tenant_a.id, store_id=store_a1.id, product_id=prod1.id, quantity=50, min_stock_level=5)
    inv_s1_p2 = Inventory(tenant_id=tenant_a.id, store_id=store_a1.id, product_id=prod2.id, quantity=4, min_stock_level=10) # Low stock (4 <= 10)
    inv_s2_p1 = Inventory(tenant_id=tenant_a.id, store_id=store_a2.id, product_id=prod1.id, quantity=0, min_stock_level=5)  # Out of stock (0 <= 0)
    inv_s2_p2 = Inventory(tenant_id=tenant_a.id, store_id=store_a2.id, product_id=prod2.id, quantity=15, min_stock_level=5)
    inv_tb = Inventory(tenant_id=tenant_b.id, store_id=store_b1.id, product_id=prod_b.id, quantity=100, min_stock_level=5)

    db.add_all([inv_s1_p1, inv_s1_p2, inv_s2_p1, inv_s2_p2, inv_tb])
    db.flush()

    # Customers
    cust1 = Customer(tenant_id=tenant_a.id, name="Rahul Sharma", email=f"rahul-{slug_a}@test.com", phone=f"91111{slug_a[:5]}")
    cust2 = Customer(tenant_id=tenant_a.id, name="Priya Patel", email=f"priya-{slug_a}@test.com", phone=f"92222{slug_a[:5]}")
    cust_b = Customer(tenant_id=tenant_b.id, name="Tenant B Cust", email=f"tb-{slug_b}@test.com", phone=f"93333{slug_b[:5]}")
    db.add_all([cust1, cust2, cust_b])
    db.flush()

    now = datetime.utcnow()

    # Orders for Store A1:
    # Order 1: cust1, total=1100 (subtotal=1000, discount=0, tax=100)
    ord_a1_1 = Order(
        tenant_id=tenant_a.id,
        store_id=store_a1.id,
        customer_id=cust1.id,
        order_number=f"ORD-A1-1-{slug_a[:4]}",
        status="delivered",
        subtotal=Decimal("1000.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("100.00"),
        total_amount=Decimal("1100.00"),
        created_at=now - timedelta(days=2),
    )
    # Order 2: Guest order (customer_id=None), total=2200 (subtotal=2000, discount=100, tax=300)
    ord_a1_2 = Order(
        tenant_id=tenant_a.id,
        store_id=store_a1.id,
        customer_id=None,
        order_number=f"ORD-A1-2-{slug_a[:4]}",
        status="confirmed",
        subtotal=Decimal("2000.00"),
        discount_amount=Decimal("100.00"),
        tax_amount=Decimal("300.00"),
        total_amount=Decimal("2200.00"),
        created_at=now - timedelta(days=1),
    )
    # Orders for Store A2:
    # Order 3: cust2, total=3300 (subtotal=3000, discount=0, tax=300)
    ord_a2_1 = Order(
        tenant_id=tenant_a.id,
        store_id=store_a2.id,
        customer_id=cust2.id,
        order_number=f"ORD-A2-1-{slug_a[:4]}",
        status="delivered",
        subtotal=Decimal("3000.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("300.00"),
        total_amount=Decimal("3300.00"),
        created_at=now - timedelta(days=1),
    )
    # Order for Tenant B (should never be seen by Tenant A):
    ord_b_1 = Order(
        tenant_id=tenant_b.id,
        store_id=store_b1.id,
        customer_id=cust_b.id,
        order_number=f"ORD-B-1-{slug_b[:4]}",
        status="delivered",
        subtotal=Decimal("10000.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("1000.00"),
        total_amount=Decimal("11000.00"),
        created_at=now - timedelta(days=1),
    )
    db.add_all([ord_a1_1, ord_a1_2, ord_a2_1, ord_b_1])
    db.flush()

    # OrderItems for COGS calculation:
    # ord_a1_1: 1 unit of prod1 (cost = 600)
    oi_1 = OrderItem(order_id=ord_a1_1.id, product_id=prod1.id, quantity=1, unit_price=Decimal("1000.00"), total_amount=Decimal("1100.00"))
    # ord_a1_2: 2 units of prod1 (cost = 2 * 600 = 1200)
    oi_2 = OrderItem(order_id=ord_a1_2.id, product_id=prod1.id, quantity=2, unit_price=Decimal("1000.00"), total_amount=Decimal("2200.00"))
    # ord_a2_1: 1 unit of prod2 (cost = 1800)
    oi_3 = OrderItem(order_id=ord_a2_1.id, product_id=prod2.id, quantity=1, unit_price=Decimal("3000.00"), total_amount=Decimal("3300.00"))
    db.add_all([oi_1, oi_2, oi_3])
    db.flush()

    # Invoices & Refunds:
    # ord_a1_1 has an invoice and an approved refund of 200.00
    inv_a1_1 = Invoice(tenant_id=tenant_a.id, order_id=ord_a1_1.id, invoice_number=f"INV-1-{slug_a[:4]}", total_amount=Decimal("1100.00"))
    db.add(inv_a1_1)
    db.flush()
    ref_a1_1 = Refund(
        tenant_id=tenant_a.id,
        invoice_id=inv_a1_1.id,
        refund_amount=Decimal("200.00"),
        refund_method="cash",
        status="approved",
        created_at=now - timedelta(days=1),
    )
    db.add(ref_a1_1)
    db.flush()

    # Store Expenses:
    # Store A1 has an active expense of 300.00
    exp_a1 = StoreExpense(
        store_id=store_a1.id,
        category="utility",
        amount=Decimal("300.00"),
        status="active",
        expense_date=date.today(),
        created_by=user_owner_a.id,
    )
    # Store A2 has an active expense of 500.00
    exp_a2 = StoreExpense(
        store_id=store_a2.id,
        category="rent",
        amount=Decimal("500.00"),
        status="active",
        expense_date=date.today(),
        created_by=user_owner_a.id,
    )
    # Store A2 has an inactive/cancelled expense of 1000.00 (should not be counted)
    exp_a2_cancelled = StoreExpense(
        store_id=store_a2.id,
        category="marketing",
        amount=Decimal("1000.00"),
        status="cancelled",
        expense_date=date.today(),
        created_by=user_owner_a.id,
    )
    db.add_all([exp_a1, exp_a2, exp_a2_cancelled])
    db.commit()

    token_owner_a = create_access_token({"sub": str(user_owner_a.id), "tenant_id": tenant_a.id, "role": "owner"})
    token_manager_s1 = create_access_token({"sub": str(user_manager_s1.id), "tenant_id": tenant_a.id, "role": "manager", "store_id": store_a1.id})
    token_cashier_a = create_access_token({"sub": str(user_cashier_a.id), "tenant_id": tenant_a.id, "role": "cashier", "store_id": store_a1.id})
    token_owner_b = create_access_token({"sub": str(user_owner_b.id), "tenant_id": tenant_b.id, "role": "owner"})

    headers_owner_a = {"Authorization": f"Bearer {token_owner_a}"}
    headers_manager_s1 = {"Authorization": f"Bearer {token_manager_s1}"}
    headers_cashier_a = {"Authorization": f"Bearer {token_cashier_a}"}
    headers_owner_b = {"Authorization": f"Bearer {token_owner_b}"}

    yield {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "store_a1": store_a1,
        "store_a2": store_a2,
        "store_a3": store_a3,
        "store_b1": store_b1,
        "headers_owner_a": headers_owner_a,
        "headers_manager_s1": headers_manager_s1,
        "headers_cashier_a": headers_cashier_a,
        "headers_owner_b": headers_owner_b,
    }

    db.close()


def test_multi_store_unauthenticated_returns_401():
    endpoints = [
        "/api/v1/multi-store/revenue-comparison",
        "/api/v1/multi-store/profit-comparison",
        "/api/v1/multi-store/inventory-comparison",
        "/api/v1/multi-store/customer-comparison",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 401, f"Expected 401 for unauthenticated request to {ep}"


def test_multi_store_unauthorized_role_returns_403(multi_store_fixture):
    headers = multi_store_fixture["headers_cashier_a"]
    endpoints = [
        "/api/v1/multi-store/revenue-comparison",
        "/api/v1/multi-store/profit-comparison",
        "/api/v1/multi-store/inventory-comparison",
        "/api/v1/multi-store/customer-comparison",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers=headers)
        assert resp.status_code == 403, f"Expected 403 for unauthorized role on {ep}"


def test_multi_store_tenant_isolation(multi_store_fixture):
    headers_a = multi_store_fixture["headers_owner_a"]
    headers_b = multi_store_fixture["headers_owner_b"]

    resp_a = client.get("/api/v1/multi-store/revenue-comparison", headers=headers_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    store_ids_a = [s["store_id"] for s in data_a["stores"]]
    assert multi_store_fixture["store_b1"].id not in store_ids_a
    assert multi_store_fixture["store_a1"].id in store_ids_a

    resp_b = client.get("/api/v1/multi-store/revenue-comparison", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    store_ids_b = [s["store_id"] for s in data_b["stores"]]
    assert multi_store_fixture["store_a1"].id not in store_ids_b
    assert multi_store_fixture["store_b1"].id in store_ids_b


def test_multi_store_cross_tenant_store_id_rejected(multi_store_fixture):
    headers_a = multi_store_fixture["headers_owner_a"]
    foreign_store_id = multi_store_fixture["store_b1"].id
    valid_store_id = multi_store_fixture["store_a1"].id

    # Sole foreign store -> 404
    resp = client.get(f"/api/v1/multi-store/revenue-comparison?store_ids={foreign_store_id}", headers=headers_a)
    assert resp.status_code == 404, "Must fail closed with 404 on cross-tenant store ID"

    # Mixed valid + foreign store -> 404 (zero partial results)
    resp_mixed = client.get(
        f"/api/v1/multi-store/revenue-comparison?store_ids={valid_store_id}&store_ids={foreign_store_id}",
        headers=headers_a,
    )
    assert resp_mixed.status_code == 404, "Must fail closed with 404 on mixed valid/foreign store IDs"


def test_multi_store_store_manager_restriction(multi_store_fixture):
    headers_mgr = multi_store_fixture["headers_manager_s1"]
    store_1_id = multi_store_fixture["store_a1"].id
    store_2_id = multi_store_fixture["store_a2"].id

    # Omitting store_ids automatically scopes manager to their assigned store (store 1)
    resp = client.get("/api/v1/multi-store/revenue-comparison", headers=headers_mgr)
    assert resp.status_code == 200
    data = resp.json()
    assert data["store_count"] == 1
    assert data["stores"][0]["store_id"] == store_1_id

    # Requesting assigned store explicitly succeeds
    resp_valid = client.get(f"/api/v1/multi-store/revenue-comparison?store_ids={store_1_id}", headers=headers_mgr)
    assert resp_valid.status_code == 200

    # Requesting another store returns 403 Forbidden
    resp_forbidden = client.get(f"/api/v1/multi-store/revenue-comparison?store_ids={store_2_id}", headers=headers_mgr)
    assert resp_forbidden.status_code == 403, "Store manager must be forbidden from accessing unassigned stores"


def test_multi_store_date_validation_reversed(multi_store_fixture):
    headers = multi_store_fixture["headers_owner_a"]
    resp = client.get(
        "/api/v1/multi-store/revenue-comparison?start_date=2026-09-20&end_date=2026-09-10",
        headers=headers,
    )
    assert resp.status_code == 400
    assert "start_date must be before or equal to end_date" in resp.json()["detail"]


def test_multi_store_revenue_comparison_metrics(multi_store_fixture):
    headers = multi_store_fixture["headers_owner_a"]
    s1_id = multi_store_fixture["store_a1"].id
    s2_id = multi_store_fixture["store_a2"].id
    s3_id = multi_store_fixture["store_a3"].id

    resp = client.get("/api/v1/multi-store/revenue-comparison", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["store_count"] == 3
    store_dict = {s["store_id"]: s for s in data["stores"]}

    # Store 1 metrics:
    # ord1: sub=1000, disc=0, tax=100, tot=1100
    # ord2: sub=2000, disc=100, tax=300, tot=2200
    # total_sales = 3300.00, gross_sales = 3000.00, disc = 100.00, tax = 400.00
    # refund = 200.00
    # net_sales = 3300 - 200 = 3100.00
    # order_count = 2, AOV = 3300 / 2 = 1650.00
    s1 = store_dict[s1_id]
    assert s1["gross_sales"] == "3000.00"
    assert s1["discount_amount"] == "100.00"
    assert s1["tax_amount"] == "400.00"
    assert s1["total_sales"] == "3300.00"
    assert s1["refund_amount"] == "200.00"
    assert s1["net_sales"] == "3100.00"
    assert s1["order_count"] == 2
    assert s1["average_order_value"] == "1650.00"

    # Store 2 metrics:
    # ord3: sub=3000, disc=0, tax=300, tot=3300, refund=0
    # net_sales = 3300.00
    s2 = store_dict[s2_id]
    assert s2["net_sales"] == "3300.00"
    assert s2["order_count"] == 1
    assert s2["average_order_value"] == "3300.00"

    # Store 3 metrics (Zero activity store):
    s3 = store_dict[s3_id]
    assert s3["net_sales"] == "0.00"
    assert s3["order_count"] == 0
    assert s3["average_order_value"] == "0.00"
    assert s3["share_of_total_revenue_pct"] == 0.0

    # Total tenant net sales = 3100 + 3300 = 6400.00
    assert data["total_tenant_net_sales"] == "6400.00"
    assert data["total_tenant_orders"] == 3

    # Ranking: Store 2 (3300) > Store 1 (3100) > Store 3 (0)
    assert data["stores"][0]["store_id"] == s2_id
    assert data["stores"][1]["store_id"] == s1_id
    assert data["stores"][2]["store_id"] == s3_id


def test_multi_store_profit_comparison_metrics(multi_store_fixture):
    headers = multi_store_fixture["headers_owner_a"]
    s1_id = multi_store_fixture["store_a1"].id
    s2_id = multi_store_fixture["store_a2"].id
    s3_id = multi_store_fixture["store_a3"].id

    resp = client.get("/api/v1/multi-store/profit-comparison", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    store_dict = {s["store_id"]: s for s in data["stores"]}

    # Store 1:
    # net_revenue = gross_sales (3000) - discounts (100) = 2900.00
    # COGS = oi1(1 * 600) + oi2(2 * 600) = 1800.00
    # gross_profit = 2900 - 1800 = 1100.00
    # operating_expenses = 300.00
    # refund_amount = 200.00
    # net_profit = 1100 - 300 - 200 = 600.00
    # margin = (600 / 2900) * 100 = 20.69%
    s1 = store_dict[s1_id]
    assert s1["net_revenue"] == "2900.00"
    assert s1["cogs"] == "1800.00"
    assert s1["operating_expenses"] == "300.00"
    assert s1["refund_amount"] == "200.00"
    assert s1["gross_profit"] == "1100.00"
    assert s1["net_profit"] == "600.00"
    assert s1["net_profit_margin_pct"] == 20.69

    # Store 2:
    # net_revenue = 3000.00 - 0 = 3000.00
    # COGS = oi3(1 * 1800) = 1800.00
    # gross_profit = 3000 - 1800 = 1200.00
    # operating_expenses = 500.00 (cancelled 1000 is ignored)
    # refund_amount = 0.00
    # net_profit = 1200 - 500 = 700.00
    # margin = (700 / 3000) * 100 = 23.33%
    s2 = store_dict[s2_id]
    assert s2["net_revenue"] == "3000.00"
    assert s2["cogs"] == "1800.00"
    assert s2["operating_expenses"] == "500.00"
    assert s2["net_profit"] == "700.00"
    assert s2["net_profit_margin_pct"] == 23.33

    # Store 3 (Zero activity):
    s3 = store_dict[s3_id]
    assert s3["net_profit"] == "0.00"
    assert s3["net_profit_margin_pct"] == 0.0

    # Sorting descending by net_profit: Store 2 (700) > Store 1 (600) > Store 3 (0)
    assert data["stores"][0]["store_id"] == s2_id
    assert data["stores"][1]["store_id"] == s1_id
    assert data["stores"][2]["store_id"] == s3_id


def test_multi_store_inventory_comparison_metrics(multi_store_fixture):
    headers = multi_store_fixture["headers_owner_a"]
    s1_id = multi_store_fixture["store_a1"].id
    s2_id = multi_store_fixture["store_a2"].id
    s3_id = multi_store_fixture["store_a3"].id

    resp = client.get("/api/v1/multi-store/inventory-comparison", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    store_dict = {s["store_id"]: s for s in data["stores"]}

    # Store 1 inventory:
    # prod1: qty=50, cost=600, sell=1000 -> cost_val=30000, sell_val=50000
    # prod2: qty=4, cost=1800, sell=3000 -> cost_val=7200, sell_val=12000
    # total_units = 54, cost_val = 37200.00, retail_val = 62000.00
    # prod2 is low stock (4 <= 10) -> low_stock_count = 1
    # out_of_stock_count = 0
    s1 = store_dict[s1_id]
    assert s1["total_products"] == 2
    assert s1["total_units"] == 54
    assert s1["cost_valuation"] == "37200.00"
    assert s1["retail_valuation"] == "62000.00"
    assert s1["low_stock_count"] == 1
    assert s1["out_of_stock_count"] == 0

    # Store 2 inventory:
    # prod1: qty=0, cost=600, sell=1000 -> cost_val=0, sell_val=0 (out of stock and low stock)
    # prod2: qty=15, cost=1800, sell=3000 -> cost_val=27000, sell_val=45000
    # total_units = 15, cost_val = 27000.00, retail_val = 45000.00
    # low_stock_count = 1 (qty 0 <= min 5), out_of_stock_count = 1 (qty 0 <= 0)
    s2 = store_dict[s2_id]
    assert s2["total_products"] == 2
    assert s2["total_units"] == 15
    assert s2["cost_valuation"] == "27000.00"
    assert s2["retail_valuation"] == "45000.00"
    assert s2["low_stock_count"] == 1
    assert s2["out_of_stock_count"] == 1

    # Store 3 (Zero inventory):
    s3 = store_dict[s3_id]
    assert s3["total_products"] == 0
    assert s3["total_units"] == 0
    assert s3["cost_valuation"] == "0.00"
    assert s3["retail_valuation"] == "0.00"

    # Sorting descending by cost_valuation: Store 1 (37200) > Store 2 (27000) > Store 3 (0)
    assert data["stores"][0]["store_id"] == s1_id
    assert data["stores"][1]["store_id"] == s2_id
    assert data["stores"][2]["store_id"] == s3_id


def test_multi_store_customer_comparison_metrics(multi_store_fixture):
    headers = multi_store_fixture["headers_owner_a"]
    s1_id = multi_store_fixture["store_a1"].id
    s2_id = multi_store_fixture["store_a2"].id
    s3_id = multi_store_fixture["store_a3"].id

    resp = client.get("/api/v1/multi-store/customer-comparison", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    store_dict = {s["store_id"]: s for s in data["stores"]}

    # Store 1:
    # ord1 has cust1, ord2 has guest (None)
    # unique_customers = 1, guest_orders = 1, total_orders = 2
    # total_spend = 1100 + 2200 = 3300.00
    # avg_bill = 3300 / 2 = 1650.00
    s1 = store_dict[s1_id]
    assert s1["unique_customers"] == 1
    assert s1["guest_orders"] == 1
    assert s1["total_orders"] == 2
    assert s1["total_spend"] == "3300.00"
    assert s1["average_bill_size"] == "1650.00"

    # Store 2:
    # ord3 has cust2
    # unique_customers = 1, guest_orders = 0, total_orders = 1
    # total_spend = 3300.00
    # avg_bill = 3300.00
    s2 = store_dict[s2_id]
    assert s2["unique_customers"] == 1
    assert s2["guest_orders"] == 0
    assert s2["total_orders"] == 1
    assert s2["total_spend"] == "3300.00"
    assert s2["average_bill_size"] == "3300.00"

    # Store 3 (Zero customer activity):
    s3 = store_dict[s3_id]
    assert s3["unique_customers"] == 0
    assert s3["guest_orders"] == 0
    assert s3["total_orders"] == 0
    assert s3["total_spend"] == "0.00"
    assert s3["average_bill_size"] == "0.00"

    assert data["total_tenant_unique_customers"] == 2
    assert data["total_tenant_orders"] == 3


def test_multi_store_expired_subscription_read_only(multi_store_fixture):
    """
    Verifies that tenants with expired subscriptions can still read multi-store comparison analytics
    per Task 6.3 read-only access behavior (operational mutations are blocked, GET analytics remain unblocked).
    """
    tenant_a = multi_store_fixture["tenant_a"]
    headers = multi_store_fixture["headers_owner_a"]

    db = SessionLocal()
    sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == tenant_a.id).first()
    sub.status = "expired"
    db.commit()
    db.close()

    endpoints = [
        "/api/v1/multi-store/revenue-comparison",
        "/api/v1/multi-store/profit-comparison",
        "/api/v1/multi-store/inventory-comparison",
        "/api/v1/multi-store/customer-comparison",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers=headers)
        assert resp.status_code == 200, f"Expired tenant should be able to read {ep}"
