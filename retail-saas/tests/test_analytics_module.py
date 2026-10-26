import random
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture
def analytics_fixture():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        tenant = Tenant(name=f"Analytics Store {suffix}", domain=f"analytics-{suffix}", is_active=True)
        db.add(tenant)
        db.flush()
        tenant_id = tenant.id

        # Roles
        owner_role = Role(tenant_id=tenant_id, name="owner", permissions=["*"], is_system=False)
        mgr_role = Role(tenant_id=tenant_id, name=f"analytics_manager_{suffix}", permissions=["analytics:read"], is_system=False)
        db.add_all([owner_role, mgr_role])
        db.flush()

        # Users
        owner_user = User(
            tenant_id=tenant_id,
            role_id=owner_role.id,
            email=f"owner_an_{suffix}@retailtest.com",
            password_hash=get_password_hash("OwnerPass123!"),
            full_name=f"Analytics Owner {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
            store_id=None,
        )
        # Create Store 1 and Store 2
        s1 = Store(name=f"Store 1 {suffix}", code=f"S1{suffix[:4].upper()}", tenant_id=tenant_id, is_active=True)
        s2 = Store(name=f"Store 2 {suffix}", code=f"S2{suffix[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([owner_user, s1, s2])
        db.flush()

        staff_user = User(
            tenant_id=tenant_id,
            store_id=s1.id,
            role_id=mgr_role.id,
            email=f"staff_{suffix}@retailtest.com",
            password_hash=get_password_hash("StaffPass123!"),
            full_name=f"Staff {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(staff_user)
        db.flush()

        owner_token = create_access_token({"sub": str(owner_user.id), "tenant_id": tenant_id})
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        staff_token = create_access_token({"sub": str(staff_user.id), "tenant_id": tenant_id})
        staff_headers = {"Authorization": f"Bearer {staff_token}"}

        # Category
        cat = Category(tenant_id=tenant_id, name=f"Category-{suffix}")
        db.add(cat)
        db.flush()

        # Create Products
        p1 = Product(
            name=f"Product Blue {suffix}",
            sku=f"SKU-BLU-{suffix}",
            category_id=cat.id,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            gst_rate=Decimal("18.00"),
            tenant_id=tenant_id,
            is_active=True,
        )
        p2 = Product(
            name=f"Product Red {suffix}",
            sku=f"SKU-RED-{suffix}",
            selling_price=Decimal("200.00"),
            cost_price=Decimal("120.00"),
            gst_rate=Decimal("18.00"),
            tenant_id=tenant_id,
            is_active=True,
        )
        # Product 3 (Dead stock item: has inventory but 0 sales)
        p3 = Product(
            name=f"Dead Product {suffix}",
            sku=f"SKU-DEAD-{suffix}",
            category_id=cat.id,
            selling_price=Decimal("150.00"),
            cost_price=Decimal("90.00"),
            gst_rate=Decimal("18.00"),
            tenant_id=tenant_id,
            is_active=True,
        )
        db.add_all([p1, p2, p3])
        db.flush()

        # Inventory for p3
        inv_dead = Inventory(
            tenant_id=tenant_id,
            store_id=s1.id,
            product_id=p3.id,
            quantity=Decimal("20.0000"),
        )
        db.add(inv_dead)
        db.flush()

        # Create Customers: c1 (2 orders), c2 (1 order), c3 (0 orders)
        c1 = Customer(name=f"Customer One {suffix}", phone=_gen_phone(), tenant_id=tenant_id)
        c2 = Customer(name=f"Customer Two {suffix}", phone=_gen_phone(), tenant_id=tenant_id)
        c3 = Customer(name=f"Customer Prospect {suffix}", phone=_gen_phone(), tenant_id=tenant_id)
        db.add_all([c1, c2, c3])
        db.flush()

        # Create Orders for Store 1:
        # Order 1 (c1): p1 x 5 (500)
        o1 = Order(
            tenant_id=tenant_id,
            store_id=s1.id,
            customer_id=c1.id,
            order_number=f"ORD-A1-{suffix}",
            total_amount=Decimal("500.00"),
            status="delivered",
            payment_status="paid",
        )
        db.add(o1)
        db.flush()
        item1 = OrderItem(order_id=o1.id, product_id=p1.id, quantity=5, unit_price=Decimal("100.00"), total_amount=Decimal("500.00"))
        db.add(item1)

        # Order 2 (c1 repeat): p2 x 2 (400)
        o2 = Order(
            tenant_id=tenant_id,
            store_id=s1.id,
            customer_id=c1.id,
            order_number=f"ORD-A2-{suffix}",
            total_amount=Decimal("400.00"),
            status="confirmed",
            payment_status="paid",
        )
        db.add(o2)
        db.flush()
        item2 = OrderItem(order_id=o2.id, product_id=p2.id, quantity=2, unit_price=Decimal("200.00"), total_amount=Decimal("400.00"))
        db.add(item2)

        # Order 3 in Store 2 (c2): p2 x 10 (2000)
        o3 = Order(
            tenant_id=tenant_id,
            store_id=s2.id,
            customer_id=c2.id,
            order_number=f"ORD-B1-{suffix}",
            total_amount=Decimal("2000.00"),
            status="delivered",
            payment_status="paid",
        )
        db.add(o3)
        db.flush()
        item3 = OrderItem(order_id=o3.id, product_id=p2.id, quantity=10, unit_price=Decimal("200.00"), total_amount=Decimal("2000.00"))
        db.add(item3)

        db.commit()

        return {
            "tenant_id": tenant_id,
            "owner_headers": owner_headers,
            "staff_headers": staff_headers,
            "store1_id": s1.id,
            "store2_id": s2.id,
            "cat_id": cat.id,
            "prod1_id": p1.id,
            "prod2_id": p2.id,
            "prod_dead_id": p3.id,
            "cust1_id": c1.id,
            "cust2_id": c2.id,
            "cust_prospect_id": c3.id,
        }
    finally:
        db.close()


def test_product_performance_analytics_consolidated_and_filtered(analytics_fixture):
    """Verify GET /api/v1/analytics/products returns product performance metrics including COGS and margins."""
    headers = analytics_fixture["owner_headers"]
    s1 = analytics_fixture["store1_id"]
    s2 = analytics_fixture["store2_id"]
    p1 = analytics_fixture["prod1_id"]
    p2 = analytics_fixture["prod2_id"]
    cat_id = analytics_fixture["cat_id"]

    # 1. Consolidated (all stores)
    res_all = client.get("/api/v1/analytics/products", headers=headers)
    assert res_all.status_code == 200, res_all.text
    data_all = res_all.json()
    assert isinstance(data_all, list)
    assert len(data_all) >= 2

    # Product 2 total revenue: 400 + 2000 = 2400, sold 12, cost 120 -> COGS 1440, Profit 960, Margin 40%
    p2_entry = next((item for item in data_all if item["product_id"] == p2), None)
    assert p2_entry is not None
    assert p2_entry["quantity_sold"] == 12
    assert p2_entry["revenue"] == pytest.approx(2400.0, 0.01)
    assert p2_entry["cost_price"] == pytest.approx(120.0, 0.01)
    assert p2_entry["cogs"] == pytest.approx(1440.0, 0.01)
    assert p2_entry["gross_profit"] == pytest.approx(960.0, 0.01)
    assert p2_entry["margin_percentage"] == pytest.approx(40.0, 0.1)

    # Product 1 check: sku, category_name
    p1_entry = next((item for item in data_all if item["product_id"] == p1), None)
    assert p1_entry is not None
    assert p1_entry["sku"] is not None
    assert p1_entry["category_name"] is not None
    assert p1_entry["quantity_sold"] == 5
    assert p1_entry["gross_profit"] == pytest.approx(200.0, 0.01)  # 500 - 300

    # 2. Filter by Store 1
    res_s1 = client.get(f"/api/v1/analytics/products?store_id={s1}", headers=headers)
    assert res_s1.status_code == 200
    data_s1 = res_s1.json()
    assert len(data_s1) == 2
    p1_s1 = next((item for item in data_s1 if item["product_id"] == p1), None)
    assert p1_s1["quantity_sold"] == 5
    assert p1_s1["revenue"] == pytest.approx(500.0, 0.01)

    # 3. Filter by Category
    res_cat = client.get(f"/api/v1/analytics/products?category_id={cat_id}", headers=headers)
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    assert len(data_cat) == 1
    assert data_cat[0]["product_id"] == p1

    # 4. Sorting by quantity asc
    res_sort = client.get("/api/v1/analytics/products?sort_by=quantity&order=asc", headers=headers)
    assert res_sort.status_code == 200
    data_sort = res_sort.json()
    assert data_sort[0]["quantity_sold"] <= data_sort[1]["quantity_sold"]

    # 5. Limit and period filters
    res_limit = client.get("/api/v1/analytics/products?limit=1", headers=headers)
    assert res_limit.status_code == 200
    assert len(res_limit.json()) == 1

    res_period = client.get("/api/v1/analytics/products?period=this_month", headers=headers)
    assert res_period.status_code == 200

    # 6. Non-existent store -> 404
    assert client.get("/api/v1/analytics/products?store_id=999999", headers=headers).status_code == 404

    # 7. Validation errors -> 422
    assert client.get("/api/v1/analytics/products?store_id=0", headers=headers).status_code == 422
    assert client.get("/api/v1/analytics/products?limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/analytics/products?period=invalid_period", headers=headers).status_code == 422


def test_customer_analytics_metrics_and_retention(analytics_fixture):
    """Verify GET /api/v1/analytics/customers returns retention, active vs zero-order counts, and KPI metrics."""
    headers = analytics_fixture["owner_headers"]
    s1 = analytics_fixture["store1_id"]
    s2 = analytics_fixture["store2_id"]

    # 1. Consolidated customer analytics
    res = client.get("/api/v1/analytics/customers", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_customers"] == 3  # c1, c2, c3
    assert data["active_customers"] == 2  # c1, c2 bought
    assert data["zero_order_customers"] == 1  # c3 has 0 orders
    assert data["repeat_customers"] == 1  # c1 has 2 orders
    assert data["one_time_customers"] == 1  # c2 has 1 order
    assert data["repeat_rate_percentage"] == pytest.approx(50.0, 0.1)  # 1/2 * 100
    assert data["total_orders"] == 3
    assert data["total_revenue"] == pytest.approx(2900.0, 0.01)
    assert data["average_order_value"] == pytest.approx(round(2900.0 / 3, 2), 0.01)

    # 2. Store 1 customer analytics
    res_s1 = client.get(f"/api/v1/analytics/customers?store_id={s1}", headers=headers)
    assert res_s1.status_code == 200
    data_s1 = res_s1.json()
    assert data_s1["total_customers"] == 1
    assert data_s1["repeat_customers"] == 1
    assert data_s1["total_orders"] == 2
    assert data_s1["total_revenue"] == pytest.approx(900.0, 0.01)

    # 3. Store 2 customer analytics
    res_s2 = client.get(f"/api/v1/analytics/customers?store_id={s2}", headers=headers)
    assert res_s2.status_code == 200
    data_s2 = res_s2.json()
    assert data_s2["total_customers"] == 1
    assert data_s2["repeat_customers"] == 0
    assert data_s2["total_orders"] == 1
    assert data_s2["total_revenue"] == pytest.approx(2000.0, 0.01)

    # 4. Period filter
    res_p = client.get("/api/v1/analytics/customers?period=this_month", headers=headers)
    assert res_p.status_code == 200

    # 5. Non-existent store -> 404
    assert client.get("/api/v1/analytics/customers?store_id=999999", headers=headers).status_code == 404


def test_dead_stock_analytics(analytics_fixture):
    """Verify GET /api/v1/analytics/dead-stock returns slow-moving and unsold items."""
    headers = analytics_fixture["owner_headers"]
    dead_prod_id = analytics_fixture["prod_dead_id"]
    s1 = analytics_fixture["store1_id"]

    res = client.get("/api/v1/analytics/dead-stock?days=30", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["threshold_days"] == 30
    assert data["total_dead_stock_items"] >= 1
    assert data["total_tied_capital"] >= 1800.0  # 20 * 90

    dead_entry = next((item for item in data["items"] if item["product_id"] == dead_prod_id), None)
    assert dead_entry is not None
    assert dead_entry["current_stock"] == 20
    assert dead_entry["cost_price"] == pytest.approx(90.0, 0.01)
    assert dead_entry["stock_value"] == pytest.approx(1800.0, 0.01)
    assert dead_entry["days_inactive"] >= 0

    # Filter by store 1
    res_s1 = client.get(f"/api/v1/analytics/dead-stock?store_id={s1}", headers=headers)
    assert res_s1.status_code == 200
    assert any(i["product_id"] == dead_prod_id for i in res_s1.json()["items"])


def test_sales_trends_analytics(analytics_fixture):
    """Verify GET /api/v1/analytics/sales-trends aggregates revenue and orders over time."""
    headers = analytics_fixture["owner_headers"]
    s1 = analytics_fixture["store1_id"]

    # Daily trend
    res_daily = client.get("/api/v1/analytics/sales-trends?interval=daily&period=this_month", headers=headers)
    assert res_daily.status_code == 200, res_daily.text
    data = res_daily.json()
    assert data["interval"] == "daily"
    assert data["total_orders"] == 3
    assert data["total_revenue"] == pytest.approx(2900.0, 0.01)
    assert len(data["trends"]) >= 1

    trend_item = data["trends"][0]
    assert "period_label" in trend_item
    assert "order_count" in trend_item
    assert "total_revenue" in trend_item
    assert "gross_profit" in trend_item
    assert "average_order_value" in trend_item

    # Hourly trend for Store 1
    res_hourly = client.get(f"/api/v1/analytics/sales-trends?interval=hourly&store_id={s1}", headers=headers)
    assert res_hourly.status_code == 200
    assert res_hourly.json()["total_orders"] == 2


def test_customer_segments_analytics(analytics_fixture):
    """Verify GET /api/v1/analytics/customer-segments performs RFM segmentation."""
    headers = analytics_fixture["owner_headers"]

    res = client.get("/api/v1/analytics/customer-segments", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_customers"] == 3
    assert len(data["segments"]) >= 1

    # Check segment names present
    seg_names = [s["segment"] for s in data["segments"]]
    assert "Champions" in seg_names or "Recent Buyers" in seg_names or "Prospects (No Orders)" in seg_names

    # Check that Prospects (No Orders) has at least 1 customer (c3)
    prospects = next((s for s in data["segments"] if s["segment"] == "Prospects (No Orders)"), None)
    assert prospects is not None
    assert prospects["customer_count"] == 1


def test_demand_forecast_analytics(analytics_fixture):
    """Verify GET /api/v1/analytics/forecast produces future sales projections."""
    headers = analytics_fixture["owner_headers"]

    res = client.get("/api/v1/analytics/forecast?days_ahead=7", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["days_ahead"] == 7
    assert len(data["forecast"]) == 7
    assert "daily_average_revenue" in data
    assert "total_forecasted_revenue" in data

    day1 = data["forecast"][0]
    assert "date" in day1
    assert "predicted_revenue" in day1
    assert "predicted_orders" in day1
    assert "confidence_score" in day1


def test_analytics_store_staff_access_control(analytics_fixture):
    """Verify store staff is isolated to assigned store across all analytics endpoints."""
    staff_headers = analytics_fixture["staff_headers"]
    s1 = analytics_fixture["store1_id"]
    s2 = analytics_fixture["store2_id"]

    # 1. Staff accessing their own store succeeds
    assert client.get(f"/api/v1/analytics/products?store_id={s1}", headers=staff_headers).status_code == 200
    assert client.get(f"/api/v1/analytics/customers?store_id={s1}", headers=staff_headers).status_code == 200
    assert client.get(f"/api/v1/analytics/dead-stock?store_id={s1}", headers=staff_headers).status_code == 200
    assert client.get(f"/api/v1/analytics/sales-trends?store_id={s1}", headers=staff_headers).status_code == 200
    assert client.get(f"/api/v1/analytics/customer-segments?store_id={s1}", headers=staff_headers).status_code == 200
    assert client.get(f"/api/v1/analytics/forecast?store_id={s1}", headers=staff_headers).status_code == 200

    # 2. Staff omitting store_id is auto-locked to their store
    res_auto_p = client.get("/api/v1/analytics/products", headers=staff_headers)
    assert res_auto_p.status_code == 200
    assert len(res_auto_p.json()) == 2

    # 3. Staff accessing Store 2 -> 403 Forbidden on all endpoints
    assert client.get(f"/api/v1/analytics/products?store_id={s2}", headers=staff_headers).status_code == 403
    assert client.get(f"/api/v1/analytics/customers?store_id={s2}", headers=staff_headers).status_code == 403
    assert client.get(f"/api/v1/analytics/dead-stock?store_id={s2}", headers=staff_headers).status_code == 403
    assert client.get(f"/api/v1/analytics/sales-trends?store_id={s2}", headers=staff_headers).status_code == 403
    assert client.get(f"/api/v1/analytics/customer-segments?store_id={s2}", headers=staff_headers).status_code == 403
    assert client.get(f"/api/v1/analytics/forecast?store_id={s2}", headers=staff_headers).status_code == 403
