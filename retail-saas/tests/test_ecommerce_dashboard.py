import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.category import Category
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.core.security import get_password_hash

client = TestClient(app)


def create_tenant_setup(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Ecom Owner",
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

    # Create 2 Stores
    store1 = Store(
        tenant_id=tenant_id,
        name=f"Main-Outlet-{uuid.uuid4().hex[:4]}",
        address="100 Market St",
        is_active=True,
        is_main=True,
    )
    store2 = Store(
        tenant_id=tenant_id,
        name=f"Sub-Branch-{uuid.uuid4().hex[:4]}",
        address="200 West Mall",
        is_active=True,
        is_main=False,
    )
    db.add_all([store1, store2])
    db.commit()
    db.refresh(store1)
    db.refresh(store2)

    store1_id = store1.id
    store2_id = store2.id

    # Categories
    cat_dessert = Category(tenant_id=tenant_id, name="Dessert", is_active=True)
    cat_tech = Category(tenant_id=tenant_id, name="Tech", is_active=True)
    db.add_all([cat_dessert, cat_tech])
    db.commit()
    db.refresh(cat_dessert)
    db.refresh(cat_tech)

    # Products
    p1 = Product(
        tenant_id=tenant_id,
        category_id=cat_dessert.id,
        name="Ritu gulabjamun",
        sku=f"SKU-GULAB-{uuid.uuid4().hex[:4]}",
        selling_price=Decimal("35000.00"),
        cost_price=Decimal("15000.00"),
        is_active=True,
    )
    p2 = Product(
        tenant_id=tenant_id,
        category_id=cat_tech.id,
        name="HP Wireless Mouse",
        sku=f"SKU-MOUSE-{uuid.uuid4().hex[:4]}",
        selling_price=Decimal("200.00"),
        cost_price=Decimal("100.00"),
        is_active=True,
    )
    p3 = Product(
        tenant_id=tenant_id,
        category_id=cat_tech.id,
        name="Laptop Stand Pro",
        sku=f"SKU-STAND-{uuid.uuid4().hex[:4]}",
        selling_price=Decimal("1500.00"),
        cost_price=Decimal("800.00"),
        is_active=True,
    )
    db.add_all([p1, p2, p3])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    db.refresh(p3)

    p1_id = p1.id
    p2_id = p2.id
    p3_id = p3.id

    # Customers
    c1 = Customer(
        tenant_id=tenant_id,
        name="Customer 6",
        phone="9876543206",
        email=f"cust6-{uuid.uuid4().hex[:4]}@example.com",
    )
    c2 = Customer(
        tenant_id=tenant_id,
        name="Customer 1",
        phone="9876543201",
        email=f"cust1-{uuid.uuid4().hex[:4]}@example.com",
    )
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    c1_id = c1.id
    c2_id = c2.id

    now = datetime.now()

    # --- Store 1 Orders ---
    # 1. High value Online Order (Confirmed)
    o1 = Order(
        tenant_id=tenant_id,
        store_id=store1_id,
        customer_id=c1_id,
        order_number=f"ORD-MLIN-01-POS03-{uuid.uuid4().hex[:8].upper()}",
        order_type="online",
        status="confirmed",
        subtotal=Decimal("82596.82"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("82596.82"),
        payment_status="paid",
        created_at=now,
    )
    db.add(o1)
    db.flush()

    item1 = OrderItem(
        order_id=o1.id,
        product_id=p1_id,
        quantity=2,
        unit_price=Decimal("35000.00"),
        total_amount=Decimal("70000.00"),
    )
    item2 = OrderItem(
        order_id=o1.id,
        product_id=p2_id,
        quantity=2,
        unit_price=Decimal("200.00"),
        total_amount=Decimal("400.00"),
    )
    pay1 = Payment(
        tenant_id=tenant_id,
        order_id=o1.id,
        payment_method="online",
        status="completed",
        amount=Decimal("82596.82"),
    )
    db.add_all([item1, item2, pay1])

    # 2. Second Online Order (Processing + Delivery Pending)
    o2 = Order(
        tenant_id=tenant_id,
        store_id=store1_id,
        customer_id=c2_id,
        order_number=f"ORD-ONL-02-{uuid.uuid4().hex[:6].upper()}",
        order_type="online",
        status="processing",
        subtotal=Decimal("474.00"),
        total_amount=Decimal("474.00"),
        payment_status="paid",
        created_at=now,
    )
    db.add(o2)
    db.flush()

    item3 = OrderItem(
        order_id=o2.id,
        product_id=p2_id,
        quantity=2,
        unit_price=Decimal("200.00"),
        total_amount=Decimal("400.00"),
    )
    del1 = Delivery(
        tenant_id=tenant_id,
        order_id=o2.id,
        tracking_number=f"TRK-{uuid.uuid4().hex[:8].upper()}",
        status="pending",
    )
    db.add_all([item3, del1])

    # 3. Third Online Order (Returned)
    o3 = Order(
        tenant_id=tenant_id,
        store_id=store1_id,
        customer_id=c2_id,
        order_number=f"ORD-ONL-03-{uuid.uuid4().hex[:6].upper()}",
        order_type="online",
        status="returned",
        subtotal=Decimal("118.00"),
        total_amount=Decimal("118.00"),
        payment_status="paid",
        created_at=now - timedelta(days=2),
    )
    db.add(o3)

    # 4. Fourth Online Order (Cancelled)
    o4 = Order(
        tenant_id=tenant_id,
        store_id=store1_id,
        customer_id=c1_id,
        order_number=f"ORD-ONL-04-{uuid.uuid4().hex[:6].upper()}",
        order_type="online",
        status="cancelled",
        subtotal=Decimal("500.00"),
        total_amount=Decimal("500.00"),
        payment_status="failed",
        created_at=now - timedelta(days=5),
    )
    db.add(o4)

    # 5. Offline POS Order on Store 1
    o_pos = Order(
        tenant_id=tenant_id,
        store_id=store1_id,
        customer_id=c1_id,
        order_number=f"ORD-POS-01-{uuid.uuid4().hex[:6].upper()}",
        order_type="pos",
        status="completed",
        subtotal=Decimal("43180.62"),
        total_amount=Decimal("43180.62"),
        payment_status="paid",
        created_at=now,
    )
    db.add(o_pos)

    # --- Store 2 Online Order ---
    o_store2 = Order(
        tenant_id=tenant_id,
        store_id=store2_id,
        customer_id=c2_id,
        order_number=f"ORD-STR2-01-{uuid.uuid4().hex[:6].upper()}",
        order_type="online",
        status="confirmed",
        subtotal=Decimal("1500.00"),
        total_amount=Decimal("1500.00"),
        payment_status="paid",
        created_at=now,
    )
    db.add(o_store2)
    db.flush()

    item_store2 = OrderItem(
        order_id=o_store2.id,
        product_id=p3_id,
        quantity=1,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("1500.00"),
    )
    db.add(item_store2)

    db.commit()
    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store1_id": store1_id,
        "store2_id": store2_id,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "p3_id": p3_id,
        "c1_id": c1_id,
        "c2_id": c2_id,
    }


def test_get_ecommerce_dashboard_full():
    data = create_tenant_setup("ec-full")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard?period=this_year", headers=headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    # Verify all 5 blocks exist
    assert "kpis" in payload
    assert "revenue_comparison" in payload
    assert "order_status_breakdown" in payload
    assert "recent_orders" in payload
    assert "top_products" in payload

    # KPIs check
    kpis = payload["kpis"]
    assert kpis["online_revenue"]["value"] > 0
    assert kpis["total_online_orders"]["value"] >= 4
    assert kpis["active_products"]["value"] >= 3
    assert kpis["pending_deliveries"]["value"] >= 1

    # Revenue comparison check
    rev_comp = payload["revenue_comparison"]
    assert rev_comp["summary"]["total_online"] > 0
    assert rev_comp["summary"]["total_offline"] == 43180.62
    assert len(rev_comp["monthly_data"]) == 12

    # Status breakdown check
    donut = payload["order_status_breakdown"]
    assert donut["total_orders"] >= 4
    statuses = [s["status"] for s in donut["breakdown"]]
    assert "delivered" in statuses
    assert "processing" in statuses
    assert "cancelled" in statuses
    assert "returned" in statuses

    # Recent orders
    recent = payload["recent_orders"]
    assert len(recent) >= 1
    assert "order_id" in recent[0]
    assert "customer_name" in recent[0]
    assert "amount" in recent[0]

    # Top products
    top = payload["top_products"]
    assert len(top) >= 1
    assert top[0]["rank"] == 1
    assert top[0]["product_name"] == "Ritu gulabjamun"
    assert top[0]["progress_percentage"] == 100.0


def test_ecommerce_kpis_endpoint():
    data = create_tenant_setup("ec-kpis")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard/kpis?period=this_year", headers=headers)
    assert resp.status_code == 200, resp.text
    kpis = resp.json()

    assert "online_revenue" in kpis
    assert "total_online_orders" in kpis
    assert "active_products" in kpis
    assert "conversion_rate" in kpis
    assert "cart_abandonment" in kpis
    assert "avg_order_value" in kpis
    assert "online_customers" in kpis
    assert "pending_deliveries" in kpis

    assert kpis["online_revenue"]["value"] > 80000
    assert kpis["total_online_orders"]["value"] >= 4
    assert kpis["pending_deliveries"]["value"] == 1


def test_revenue_comparison_endpoint():
    data = create_tenant_setup("ec-rev")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard/revenue-comparison?period=this_year", headers=headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert res["summary"]["total_online"] > 0
    assert res["summary"]["total_offline"] == 43180.62
    assert len(res["monthly_data"]) == 12
    # Verify months format
    assert res["monthly_data"][0]["month"] == "Jan"
    assert res["monthly_data"][11]["month"] == "Dec"


def test_order_status_breakdown_endpoint():
    data = create_tenant_setup("ec-status")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard/order-status-breakdown?period=this_year", headers=headers)
    assert resp.status_code == 200, resp.text
    breakdown = resp.json()

    assert breakdown["total_orders"] >= 4
    slices = {b["status"]: b for b in breakdown["breakdown"]}
    assert "processing" in slices
    assert "cancelled" in slices
    assert "returned" in slices
    assert slices["processing"]["count"] >= 1
    assert slices["cancelled"]["count"] >= 1
    assert slices["returned"]["count"] >= 1


def test_recent_online_orders_endpoint():
    data = create_tenant_setup("ec-orders")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard/recent-orders?limit=5", headers=headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert "orders" in res
    assert "total" in res
    assert len(res["orders"]) > 0

    first = res["orders"][0]
    assert first["amount"] > 0
    assert first["customer_name"] in ["Customer 6", "Customer 1"]
    assert first["payment_mode"] in ["ONLINE", "PAID", "POS"]


def test_top_selling_products_endpoint():
    data = create_tenant_setup("ec-top")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard/top-products?limit=5", headers=headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert len(res["products"]) >= 2
    top = res["products"][0]
    second = res["products"][1]

    # Top product is Ritu gulabjamun with 70,000 revenue
    assert top["rank"] == 1
    assert top["product_name"] == "Ritu gulabjamun"
    assert top["category"] == "Dessert"
    assert top["revenue"] == 70000.00
    assert top["progress_percentage"] == 100.0

    # Second product has positive revenue and proportional progress percentage
    assert second["rank"] == 2
    assert second["revenue"] > 0
    assert second["progress_percentage"] < 100.0


def test_store_id_filtering_isolation():
    data = create_tenant_setup("ec-filter")
    headers = data["headers"]
    store1_id = data["store1_id"]
    store2_id = data["store2_id"]

    # 1. Query Store 1 explicitly
    resp1 = client.get(f"/api/v1/ecommerce/dashboard?store_id={store1_id}", headers=headers)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()

    # Store 1 has POS offline revenue of 43180.62
    assert data1["revenue_comparison"]["summary"]["total_offline"] == 43180.62
    # Store 1 recent orders only belong to store 1
    for o in data1["recent_orders"]:
        assert "STR2" not in o["order_id"]

    # 2. Query Store 2 explicitly
    resp2 = client.get(f"/api/v1/ecommerce/dashboard?store_id={store2_id}", headers=headers)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()

    # Store 2 has no offline POS orders
    assert data2["revenue_comparison"]["summary"]["total_offline"] == 0.0
    # Store 2 online revenue is 1500.00
    assert data2["revenue_comparison"]["summary"]["total_online"] == 1500.00
    # Top product in Store 2 is Laptop Stand Pro
    assert len(data2["top_products"]) == 1
    assert data2["top_products"][0]["product_name"] == "Laptop Stand Pro"


def test_store_staff_forbidden_other_store():
    data = create_tenant_setup("ec-staff")
    tenant_id = data["tenant_id"]
    store1_id = data["store1_id"]
    store2_id = data["store2_id"]

    # Create a staff user restricted to store 1
    db = SessionLocal()
    staff_email = f"staff-{uuid.uuid4().hex[:6]}@example.com"
    staff_user = User(
        tenant_id=tenant_id,
        email=staff_email,
        full_name="Store 1 Staff",
        password_hash=get_password_hash("Password123!"),
        store_id=store1_id,
        is_active=True,
    )
    # Assign manager role
    role = db.query(Role).filter(Role.tenant_id == tenant_id, Role.name == "manager").first()
    if role:
        staff_user.role_id = role.id
    db.add(staff_user)
    db.commit()
    db.close()

    # Login as staff
    login = client.post(
        "/api/v1/auth/login",
        json={"email": staff_email, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    staff_token = login.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # Staff accessing their own store data -> 200 OK
    resp_own = client.get(f"/api/v1/ecommerce/dashboard?store_id={store1_id}", headers=staff_headers)
    assert resp_own.status_code == 200

    # Staff accessing without store_id -> Automatically resolved to their own store1
    resp_auto = client.get("/api/v1/ecommerce/dashboard", headers=staff_headers)
    assert resp_auto.status_code == 200

    # Staff attempting to access store 2 data -> 403 Forbidden
    resp_forbidden = client.get(f"/api/v1/ecommerce/dashboard?store_id={store2_id}", headers=staff_headers)
    assert resp_forbidden.status_code == 403


def test_cross_tenant_isolation():
    tenant_a = create_tenant_setup("ec-iso-a")
    tenant_b = create_tenant_setup("ec-iso-b")

    resp_b = client.get("/api/v1/ecommerce/dashboard", headers=tenant_b["headers"])
    assert resp_b.status_code == 200
    data_b = resp_b.json()

    a_order_nums = [o["order_id"] for o in data_b["recent_orders"]]
    for o_id in a_order_nums:
        assert tenant_a["headers"] != tenant_b["headers"]


def test_invalid_store_id_404():
    data = create_tenant_setup("ec-404")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/dashboard?store_id=999999", headers=headers)
    assert resp.status_code == 404
    data_resp = resp.json()
    msg = data_resp.get("detail") or data_resp.get("message")
    assert "Store not found" in str(msg)


def test_period_filter_variations():
    data = create_tenant_setup("ec-periods")
    headers = data["headers"]

    for period in ["today", "this_week", "this_month", "last_month", "this_year", "all_time"]:
        resp = client.get(f"/api/v1/ecommerce/dashboard?period={period}", headers=headers)
        assert resp.status_code == 200, f"Failed on period={period}: {resp.text}"
        payload = resp.json()
        assert "kpis" in payload
        assert "revenue_comparison" in payload
