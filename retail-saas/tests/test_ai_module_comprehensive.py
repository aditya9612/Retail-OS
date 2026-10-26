import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.store import Store
from app.utils.constants import OrderStatus

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture(scope="module")
def ai_test_setup():
    suffix = uuid.uuid4().hex[:6]
    email = f"ai_owner_{suffix}@retailtest.com"
    domain = f"ai-tenant-{suffix}"
    password = "Password123!"

    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"AI Superstore {suffix}",
            "domain": domain,
            "owner_email": email,
            "owner_name": "AI Admin",
            "password": password,
            "owner_phone": _gen_phone(),
            "plan_code": "enterprise",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        # Create Store A & Store B
        store_a = Store(tenant_id=tenant_id, name=f"Store Alpha {suffix}", code=f"STA_{suffix}", is_active=True)
        store_b = Store(tenant_id=tenant_id, name=f"Store Beta {suffix}", code=f"STB_{suffix}", is_active=True)
        db.add_all([store_a, store_b])
        db.commit()
        db.refresh(store_a)
        db.refresh(store_b)

        # Create Category
        cat_groceries = Category(tenant_id=tenant_id, name="Groceries", is_active=True)
        cat_electronics = Category(tenant_id=tenant_id, name="Electronics", is_active=True)
        db.add_all([cat_groceries, cat_electronics])
        db.commit()
        db.refresh(cat_groceries)
        db.refresh(cat_electronics)

        # Create Products
        p1 = Product(
            tenant_id=tenant_id,
            category_id=cat_groceries.id,
            name="Organic Milk 1L",
            sku=f"MILK_{suffix}",
            selling_price=Decimal("60.00"),
            cost_price=Decimal("45.00"),
            is_active=True,
        )
        p2 = Product(
            tenant_id=tenant_id,
            category_id=cat_groceries.id,
            name="Whole Wheat Bread",
            sku=f"BREAD_{suffix}",
            selling_price=Decimal("40.00"),
            cost_price=Decimal("25.00"),
            is_active=True,
        )
        p3 = Product(
            tenant_id=tenant_id,
            category_id=cat_electronics.id,
            name="Wireless Earbuds",
            sku=f"EARBUD_{suffix}",
            selling_price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            is_active=True,
        )
        p4_dead = Product(
            tenant_id=tenant_id,
            category_id=cat_electronics.id,
            name="Vintage Calculator",
            sku=f"CALC_{suffix}",
            selling_price=Decimal("500.00"),
            cost_price=Decimal("300.00"),
            is_active=True,
        )
        db.add_all([p1, p2, p3, p4_dead])
        db.commit()
        db.refresh(p1)
        db.refresh(p2)
        db.refresh(p3)
        db.refresh(p4_dead)

        # Create Inventory (p1 is below min stock -> trigger reorder)
        inv1 = Inventory(
            tenant_id=tenant_id,
            store_id=store_a.id,
            product_id=p1.id,
            quantity=3,
            min_stock_level=10,
            max_stock_level=50,
            reorder_point=15,
        )
        inv2 = Inventory(
            tenant_id=tenant_id,
            store_id=store_a.id,
            product_id=p2.id,
            quantity=25,
            min_stock_level=10,
            max_stock_level=50,
            reorder_point=15,
        )
        inv3 = Inventory(
            tenant_id=tenant_id,
            store_id=store_a.id,
            product_id=p3.id,
            quantity=15,
            min_stock_level=5,
            max_stock_level=30,
            reorder_point=8,
        )
        inv4_slow = Inventory(
            tenant_id=tenant_id,
            store_id=store_a.id,
            product_id=p4_dead.id,
            quantity=40,
            min_stock_level=5,
            max_stock_level=50,
            reorder_point=10,
        )
        db.add_all([inv1, inv2, inv3, inv4_slow])
        db.commit()

        # Create Customers
        cust_active = Customer(
            tenant_id=tenant_id,
            name="Aarav Sharma",
            phone=_gen_phone(),
            email=f"aarav_{suffix}@example.com",
        )
        cust_churn = Customer(
            tenant_id=tenant_id,
            name="Neha Deshmukh",
            phone=_gen_phone(),
            email=f"neha_{suffix}@example.com",
        )
        cust_new = Customer(
            tenant_id=tenant_id,
            name="Rahul Patil",
            phone=_gen_phone(),
            email=f"rahul_{suffix}@example.com",
        )
        db.add_all([cust_active, cust_churn, cust_new])
        db.commit()
        db.refresh(cust_active)
        db.refresh(cust_churn)
        db.refresh(cust_new)

        # Create Completed Orders for Active Customer (buying Milk + Bread together today)
        ord1 = Order(
            tenant_id=tenant_id,
            store_id=store_a.id,
            customer_id=cust_active.id,
            order_number=f"ORD-1-{suffix}",
            status=OrderStatus.CONFIRMED.value,
            total_amount=Decimal("100.00"),
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add(ord1)
        db.commit()
        db.refresh(ord1)

        db.add_all(
            [
                OrderItem(order_id=ord1.id, product_id=p1.id, quantity=1, unit_price=Decimal("60.00"), total_amount=Decimal("60.00")),
                OrderItem(order_id=ord1.id, product_id=p2.id, quantity=1, unit_price=Decimal("40.00"), total_amount=Decimal("40.00")),
            ]
        )

        ord2 = Order(
            tenant_id=tenant_id,
            store_id=store_a.id,
            customer_id=cust_active.id,
            order_number=f"ORD-2-{suffix}",
            status=OrderStatus.DELIVERED.value,
            total_amount=Decimal("200.00"),
            created_at=datetime.utcnow() - timedelta(days=5),
        )
        db.add(ord2)
        db.commit()
        db.refresh(ord2)

        db.add_all(
            [
                OrderItem(order_id=ord2.id, product_id=p1.id, quantity=2, unit_price=Decimal("60.00"), total_amount=Decimal("120.00")),
                OrderItem(order_id=ord2.id, product_id=p2.id, quantity=2, unit_price=Decimal("40.00"), total_amount=Decimal("80.00")),
            ]
        )

        # Churned Customer placed order 70 days ago
        ord_old = Order(
            tenant_id=tenant_id,
            store_id=store_a.id,
            customer_id=cust_churn.id,
            order_number=f"ORD-OLD-{suffix}",
            status=OrderStatus.DELIVERED.value,
            total_amount=Decimal("1999.00"),
            created_at=datetime.utcnow() - timedelta(days=70),
        )
        db.add(ord_old)
        db.commit()
        db.refresh(ord_old)

        db.add(
            OrderItem(order_id=ord_old.id, product_id=p3.id, quantity=1, unit_price=Decimal("1999.00"), total_amount=Decimal("1999.00"))
        )
        db.commit()

        return {
            "tenant_id": tenant_id,
            "headers": headers,
            "store_a_id": store_a.id,
            "store_b_id": store_b.id,
            "p1_id": p1.id,
            "p1_name": p1.name,
            "p1_sku": p1.sku,
            "p2_id": p2.id,
            "p2_name": p2.name,
            "p3_id": p3.id,
            "p4_dead_id": p4_dead.id,
            "cust_active_id": cust_active.id,
            "cust_active_name": cust_active.name,
            "cust_churn_id": cust_churn.id,
            "cust_new_id": cust_new.id,
        }
    finally:
        db.close()


def test_reorder_prediction_with_sales_velocity_and_urgency(ai_test_setup):
    headers = ai_test_setup["headers"]
    store_a_id = ai_test_setup["store_a_id"]
    p1_id = ai_test_setup["p1_id"]
    p1_name = ai_test_setup["p1_name"]
    p1_sku = ai_test_setup["p1_sku"]

    resp = client.get(f"/api/v1/ai/reorder-prediction?store_id={store_a_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()

    assert len(items) >= 1
    p1_item = next((i for i in items if i["product_id"] == p1_id), None)
    assert p1_item is not None
    assert p1_item["product_name"] == p1_name
    assert p1_item["sku"] == p1_sku
    assert p1_item["current_stock"] == 3
    assert p1_item["min_stock_level"] == 10
    assert p1_item["daily_run_rate"] > 0
    assert p1_item["urgency"] in ("CRITICAL", "HIGH", "MEDIUM")
    assert p1_item["recommended_order"] > 0


def test_demand_forecast_dynamic_days_and_trend(ai_test_setup):
    headers = ai_test_setup["headers"]
    p1_id = ai_test_setup["p1_id"]
    p1_name = ai_test_setup["p1_name"]

    # Test with default 30 days
    resp30 = client.get(f"/api/v1/ai/demand-forecast/{p1_id}?days=30", headers=headers)
    assert resp30.status_code == 200, resp30.text
    data30 = resp30.json()
    assert data30["product_id"] == p1_id
    assert data30["product_name"] == p1_name
    assert data30["period_days"] == 30
    assert data30["total_sold"] == 3
    assert data30["daily_average"] == round(3.0 / 30.0, 2)
    assert "trend" in data30

    # Test with 7 days - verifies the division bug is fixed (divides by 7, not 30!)
    resp7 = client.get(f"/api/v1/ai/demand-forecast/{p1_id}?days=7", headers=headers)
    assert resp7.status_code == 200, resp7.text
    data7 = resp7.json()
    assert data7["period_days"] == 7
    assert data7["total_sold"] == 3
    assert data7["daily_average"] == round(3.0 / 7.0, 2)
    assert data7["forecast_next_7_days"] == round((3.0 / 7.0) * 7, 0)


def test_demand_forecast_missing_product_404(ai_test_setup):
    headers = ai_test_setup["headers"]
    resp = client.get("/api/v1/ai/demand-forecast/999999", headers=headers)
    assert resp.status_code == 404


def test_best_sellers_sorting_and_time_period(ai_test_setup):
    headers = ai_test_setup["headers"]
    store_a_id = ai_test_setup["store_a_id"]
    p3_id = ai_test_setup["p3_id"]

    # Sorted by quantity
    resp_qty = client.get(f"/api/v1/ai/best-sellers?sort_by=quantity&store_id={store_a_id}", headers=headers)
    assert resp_qty.status_code == 200, resp_qty.text
    items_qty = resp_qty.json()
    assert len(items_qty) >= 2
    # p1 or p2 had 3 units, p3 had 1 unit -> p1/p2 should be above p3
    assert items_qty[0]["quantity_sold"] >= items_qty[-1]["quantity_sold"]

    # Sorted by revenue (p3: 1 x 1999 = 1999, p1: 3 x 60 = 180 -> p3 should be #1!)
    resp_rev = client.get(f"/api/v1/ai/best-sellers?sort_by=revenue&store_id={store_a_id}", headers=headers)
    assert resp_rev.status_code == 200, resp_rev.text
    items_rev = resp_rev.json()
    assert items_rev[0]["product_id"] == p3_id
    assert items_rev[0]["total_revenue"] == 1999.00


def test_customer_purchase_patterns_comprehensive(ai_test_setup):
    headers = ai_test_setup["headers"]
    cust_active_id = ai_test_setup["cust_active_id"]
    cust_active_name = ai_test_setup["cust_active_name"]

    resp = client.get(f"/api/v1/ai/customer-patterns/{cust_active_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["customer_id"] == cust_active_id
    assert data["customer_name"] == cust_active_name
    assert data["order_count"] == 2
    assert data["total_spent"] == 300.00
    assert data["average_order_value"] == 150.00
    assert data["preferred_category"] == "Groceries"
    assert data["days_since_last_purchase"] is not None


def test_smart_offer_recommendations_actionable(ai_test_setup):
    headers = ai_test_setup["headers"]
    cust_churn_id = ai_test_setup["cust_churn_id"]
    cust_new_id = ai_test_setup["cust_new_id"]

    # Churned customer should get Winback coupon
    resp_churn = client.get(f"/api/v1/ai/offer-recommendations/{cust_churn_id}", headers=headers)
    assert resp_churn.status_code == 200, resp_churn.text
    offers_churn = resp_churn.json()
    assert any(o["type"] == "winback" and o["coupon_code"] == "COMEBACK15" for o in offers_churn)

    # New customer with 0 orders gets Welcome coupon
    resp_new = client.get(f"/api/v1/ai/offer-recommendations/{cust_new_id}", headers=headers)
    assert resp_new.status_code == 200, resp_new.text
    offers_new = resp_new.json()
    assert any(o["type"] == "welcome" and o["coupon_code"] == "WELCOME5" for o in offers_new)


def test_frequently_bought_together(ai_test_setup):
    headers = ai_test_setup["headers"]
    p1_id = ai_test_setup["p1_id"]
    p2_id = ai_test_setup["p2_id"]
    p2_name = ai_test_setup["p2_name"]

    # Milk was bought with Bread in 2 orders
    resp = client.get(f"/api/v1/ai/frequently-bought-together/{p1_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()

    assert len(items) >= 1
    assert items[0]["product_id"] == p2_id
    assert items[0]["product_name"] == p2_name
    assert items[0]["co_occurrence_count"] >= 2
    assert items[0]["correlation_percentage"] > 0


def test_customer_churn_risk(ai_test_setup):
    headers = ai_test_setup["headers"]
    cust_churn_id = ai_test_setup["cust_churn_id"]

    resp = client.get("/api/v1/ai/customer-churn-risk?inactive_days=45", headers=headers)
    assert resp.status_code == 200, resp.text
    churn_list = resp.json()

    assert any(c["customer_id"] == cust_churn_id for c in churn_list)
    churn_entry = next(c for c in churn_list if c["customer_id"] == cust_churn_id)
    assert churn_entry["days_inactive"] >= 45
    assert churn_entry["risk_level"] in ("CRITICAL", "HIGH")
    assert "recommended_action" in churn_entry


def test_slow_moving_dead_stock(ai_test_setup):
    headers = ai_test_setup["headers"]
    p4_dead_id = ai_test_setup["p4_dead_id"]

    # Calculator has 40 units in stock and 0 sales
    resp = client.get("/api/v1/ai/slow-moving-stock?days=30&threshold_sales=1", headers=headers)
    assert resp.status_code == 200, resp.text
    slow_items = resp.json()

    assert any(item["product_id"] == p4_dead_id for item in slow_items)
    item = next(i for i in slow_items if i["product_id"] == p4_dead_id)
    assert item["quantity_sold_in_period"] == 0
    assert item["stock_value"] > 0
    assert item["recommended_discount_percent"] >= 20


def test_ai_chat_query_assistant(ai_test_setup):
    headers = ai_test_setup["headers"]
    store_a_id = ai_test_setup["store_a_id"]

    # Query 1: Today's sales
    res1 = client.post(
        "/api/v1/ai/chat-query",
        json={"query": "What are today's sales for Store Alpha?", "store_id": store_a_id},
        headers=headers,
    )
    assert res1.status_code == 200, res1.text
    d1 = res1.json()
    assert d1["intent"] == "today_sales"
    assert "sales" in d1["answer"].lower()
    assert len(d1["suggested_actions"]) > 0

    # Query 2: Best sellers
    res2 = client.post(
        "/api/v1/ai/chat-query",
        json={"query": "Show me the top product and best seller"},
        headers=headers,
    )
    assert res2.status_code == 200, res2.text
    d2 = res2.json()
    assert d2["intent"] == "best_sellers"

    # Query 3: Low stock alerts
    res3 = client.post(
        "/api/v1/ai/chat-query",
        json={"query": "How many items are low in stock?"},
        headers=headers,
    )
    assert res3.status_code == 200, res3.text
    d3 = res3.json()
    assert d3["intent"] == "stock_alerts"

    # Query 4: Customer stats
    res4 = client.post(
        "/api/v1/ai/chat-query",
        json={"query": "How many total customers do we have?"},
        headers=headers,
    )
    assert res4.status_code == 200, res4.text
    d4 = res4.json()
    assert d4["intent"] == "customer_stats"
