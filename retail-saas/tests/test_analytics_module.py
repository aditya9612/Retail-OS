import random
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture
def analytics_fixture():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # Register tenant
        owner_email = f"owner_an_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Analytics Store {suffix}",
                "domain": f"analytics-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Analytics Owner {suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_res.status_code == 200, reg_res.text
        tenant_id = reg_res.json()["tenant_id"]

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": owner_pass},
        )
        assert login_res.status_code == 200
        owner_token = login_res.json()["access_token"]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # Create Store 1 and Store 2
        s1 = Store(name=f"Store 1 {suffix}", code=f"S1{suffix[:4].upper()}", tenant_id=tenant_id, is_active=True)
        s2 = Store(name=f"Store 2 {suffix}", code=f"S2{suffix[:4].upper()}", tenant_id=tenant_id, is_active=True)
        db.add_all([s1, s2])
        db.flush()

        # Create Products
        p1 = Product(
            name=f"Product Blue {suffix}",
            sku=f"SKU-BLU-{suffix}",
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
        db.add_all([p1, p2])
        db.flush()

        # Create Customers
        c1 = Customer(name=f"Customer One {suffix}", phone=_gen_phone(), tenant_id=tenant_id)
        c2 = Customer(name=f"Customer Two {suffix}", phone=_gen_phone(), tenant_id=tenant_id)
        db.add_all([c1, c2])
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

        # Create Manager Role with analytics:read permissions
        mgr_role = Role(
            tenant_id=tenant_id,
            name=f"analytics_manager_{suffix}",
            is_system=False,
            permissions=["analytics:read"],
        )
        db.add(mgr_role)
        db.flush()

        # Create Store 1 Staff user
        staff_email = f"staff_{suffix}@retailtest.com"
        staff_pass = "StaffPass123!"
        staff_user = User(
            tenant_id=tenant_id,
            store_id=s1.id,
            role_id=mgr_role.id,
            email=staff_email,
            password_hash=get_password_hash(staff_pass),
            full_name=f"Staff {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(staff_user)
        db.commit()

        login_staff = client.post(
            "/api/v1/auth/login",
            json={"email": staff_email, "password": staff_pass},
        )
        assert login_staff.status_code == 200
        staff_token = login_staff.json()["access_token"]
        staff_headers = {"Authorization": f"Bearer {staff_token}"}

        return {
            "tenant_id": tenant_id,
            "owner_headers": owner_headers,
            "staff_headers": staff_headers,
            "store1_id": s1.id,
            "store2_id": s2.id,
            "prod1_id": p1.id,
            "prod2_id": p2.id,
            "cust1_id": c1.id,
            "cust2_id": c2.id,
        }
    finally:
        db.close()


def test_product_performance_analytics_consolidated_and_filtered(analytics_fixture):
    """Verify GET /api/v1/analytics/products returns product performance metrics."""
    headers = analytics_fixture["owner_headers"]
    s1 = analytics_fixture["store1_id"]
    s2 = analytics_fixture["store2_id"]
    p1 = analytics_fixture["prod1_id"]
    p2 = analytics_fixture["prod2_id"]

    # 1. Consolidated (all stores)
    res_all = client.get("/api/v1/analytics/products", headers=headers)
    assert res_all.status_code == 200, res_all.text
    data_all = res_all.json()
    assert isinstance(data_all, list)
    assert len(data_all) >= 2
    # Product 2 total revenue: 400 + 2000 = 2400
    p2_entry = next((item for item in data_all if item["product_id"] == p2), None)
    assert p2_entry is not None
    assert p2_entry["quantity_sold"] == 12
    assert p2_entry["revenue"] == pytest.approx(2400.0, 0.01)

    # 2. Filter by Store 1
    res_s1 = client.get(f"/api/v1/analytics/products?store_id={s1}", headers=headers)
    assert res_s1.status_code == 200
    data_s1 = res_s1.json()
    assert len(data_s1) == 2
    p1_s1 = next((item for item in data_s1 if item["product_id"] == p1), None)
    assert p1_s1["quantity_sold"] == 5
    assert p1_s1["revenue"] == pytest.approx(500.0, 0.01)

    # 3. Filter by Store 2
    res_s2 = client.get(f"/api/v1/analytics/products?store_id={s2}", headers=headers)
    assert res_s2.status_code == 200
    data_s2 = res_s2.json()
    assert len(data_s2) == 1
    assert data_s2[0]["product_id"] == p2
    assert data_s2[0]["quantity_sold"] == 10

    # 4. Limit parameter
    res_limit = client.get("/api/v1/analytics/products?limit=1", headers=headers)
    assert res_limit.status_code == 200
    assert len(res_limit.json()) == 1

    # 5. Period filter
    res_period = client.get("/api/v1/analytics/products?period=this_month", headers=headers)
    assert res_period.status_code == 200

    # 6. Non-existent store -> 404
    assert client.get("/api/v1/analytics/products?store_id=999999", headers=headers).status_code == 404

    # 7. Validation errors -> 422
    assert client.get("/api/v1/analytics/products?store_id=0", headers=headers).status_code == 422
    assert client.get("/api/v1/analytics/products?limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/analytics/products?period=invalid_period", headers=headers).status_code == 422


def test_customer_analytics_metrics_and_retention(analytics_fixture):
    """Verify GET /api/v1/analytics/customers returns retention and KPI metrics."""
    headers = analytics_fixture["owner_headers"]
    s1 = analytics_fixture["store1_id"]
    s2 = analytics_fixture["store2_id"]

    # 1. Consolidated customer analytics
    res = client.get("/api/v1/analytics/customers", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_customers"] >= 2
    assert data["repeat_customers"] >= 1  # Customer 1 placed 2 orders
    assert "one_time_customers" in data
    assert "repeat_rate_percentage" in data
    assert "total_orders" in data
    assert "total_revenue" in data
    assert "average_order_value" in data
    assert data["total_revenue"] >= 2900.0

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
    assert data_s2["repeat_customers"] == 0  # Customer 2 has only 1 order
    assert data_s2["total_orders"] == 1
    assert data_s2["total_revenue"] == pytest.approx(2000.0, 0.01)

    # 4. Non-existent store -> 404
    assert client.get("/api/v1/analytics/customers?store_id=999999", headers=headers).status_code == 404

    # 5. Invalid store_id validation error -> 422
    assert client.get("/api/v1/analytics/customers?store_id=0", headers=headers).status_code == 422


def test_analytics_store_staff_access_control(analytics_fixture):
    """Verify store staff is isolated to assigned store on analytics endpoints."""
    staff_headers = analytics_fixture["staff_headers"]
    s1 = analytics_fixture["store1_id"]
    s2 = analytics_fixture["store2_id"]

    # 1. Staff accessing their own store succeeds
    res_own_p = client.get(f"/api/v1/analytics/products?store_id={s1}", headers=staff_headers)
    assert res_own_p.status_code == 200

    res_own_c = client.get(f"/api/v1/analytics/customers?store_id={s1}", headers=staff_headers)
    assert res_own_c.status_code == 200

    # 2. Staff omitting store_id is auto-locked to their store
    res_auto_p = client.get("/api/v1/analytics/products", headers=staff_headers)
    assert res_auto_p.status_code == 200
    assert len(res_auto_p.json()) == 2

    res_auto_c = client.get("/api/v1/analytics/customers", headers=staff_headers)
    assert res_auto_c.status_code == 200
    assert res_auto_c.json()["total_customers"] == 1

    # 3. Staff accessing Store 2 -> 403 Forbidden
    assert client.get(f"/api/v1/analytics/products?store_id={s2}", headers=staff_headers).status_code == 403
    assert client.get(f"/api/v1/analytics/customers?store_id={s2}", headers=staff_headers).status_code == 403

