import random
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


def _setup_multi_store_fixture():
    """
    Sets up:
    - Tenant 1 with Owner (store_id=None)
    - Store 1 ("Alpha Mart") & Store 2 ("Beta Mart") in Tenant 1
    - Store 1 Staff user (store_id=Store 1)
    - Products & Inventory in Store 1 & Store 2
    - Orders in Store 1 (e.g. 1500) and Store 2 (e.g. 2500)
    - Tenant 2 with Store 3 (Cross-tenant store)
    """
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # 1. Register Tenant 1
        owner_email = f"owner_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Retail MultiStore {suffix}",
                "domain": f"multi-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Owner {suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_res.status_code == 200, f"Register failed: {reg_res.text}"
        tenant1_id = reg_res.json()["tenant_id"]

        login_owner = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": owner_pass},
        )
        assert login_owner.status_code == 200
        owner_token = login_owner.json()["access_token"]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # 2. Create Store 1 & Store 2 in Tenant 1
        s1_res = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Alpha Mart {suffix}", "code": f"A1{suffix[:4].upper()}"},
        )
        assert s1_res.status_code == 201, s1_res.text
        store1_id = s1_res.json()["id"]
        store1_name = s1_res.json()["name"]

        s2_res = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Beta Mart {suffix}", "code": f"B1{suffix[:4].upper()}"},
        )
        assert s2_res.status_code == 201, s2_res.text
        store2_id = s2_res.json()["id"]
        store2_name = s2_res.json()["name"]

        # 3. Create Manager Role with dashboard permissions for Tenant 1
        mgr_role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant1_id, Role.name == "store_manager")
            .first()
        )
        if not mgr_role:
            mgr_role = Role(
                tenant_id=tenant1_id,
                name="store_manager",
                is_system=False,
                permissions=["dashboard:view", "dashboard:read", "stores:read"],
            )
            db.add(mgr_role)
            db.commit()
            db.refresh(mgr_role)

        # 4. Create Staff user assigned to Store 1
        staff_email = f"staff_s1_{suffix}@retailtest.com"
        staff_pass = "StaffPass123!"
        staff_user = User(
            tenant_id=tenant1_id,
            store_id=store1_id,
            role_id=mgr_role.id,
            email=staff_email,
            password_hash=get_password_hash(staff_pass),
            full_name=f"Staff S1 {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(staff_user)
        db.commit()
        db.refresh(staff_user)

        login_staff = client.post(
            "/api/v1/auth/login",
            json={"email": staff_email, "password": staff_pass},
        )
        assert login_staff.status_code == 200, f"Staff login failed: {login_staff.text}"
        staff_token = login_staff.json()["access_token"]
        staff_headers = {"Authorization": f"Bearer {staff_token}"}

        # 5. Create Customer in Tenant 1
        customer = Customer(
            tenant_id=tenant1_id,
            name=f"Customer {suffix}",
            phone=_gen_phone(),
            email=f"cust_{suffix}@test.com",
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)

        # 6. Create Products in Tenant 1
        p1 = Product(
            tenant_id=tenant1_id,
            name=f"Product S1 {suffix}",
            sku=f"SKU1-{suffix}",
            price=Decimal("500.00"),
            mrp=Decimal("500.00"),
            cost_price=Decimal("300.00"),
            is_active=True,
        )
        p2 = Product(
            tenant_id=tenant1_id,
            name=f"Product S2 {suffix}",
            sku=f"SKU2-{suffix}",
            price=Decimal("1000.00"),
            mrp=Decimal("1000.00"),
            cost_price=Decimal("600.00"),
            is_active=True,
        )
        db.add_all([p1, p2])
        db.commit()
        db.refresh(p1)
        db.refresh(p2)

        # 7. Create Inventory: Store 1 low stock (quantity 2 <= min 5), Store 2 normal (quantity 50 > min 5)
        inv1 = Inventory(
            tenant_id=tenant1_id,
            store_id=store1_id,
            product_id=p1.id,
            quantity=2,
            min_stock_level=5,
            max_stock_level=100,
            reorder_point=5,
        )
        inv2 = Inventory(
            tenant_id=tenant1_id,
            store_id=store2_id,
            product_id=p2.id,
            quantity=50,
            min_stock_level=5,
            max_stock_level=100,
            reorder_point=5,
        )
        db.add_all([inv1, inv2])
        db.commit()

        # 8. Create Orders:
        # Store 1: 1 order of 1500.00 today
        now = datetime.now()
        o1 = Order(
            tenant_id=tenant1_id,
            store_id=store1_id,
            customer_id=customer.id,
            order_number=f"ORD-S1-{suffix}",
            order_type="pos",
            status="completed",
            subtotal=Decimal("1500.00"),
            total_amount=Decimal("1500.00"),
            payment_status="paid",
            created_at=now,
        )
        db.add(o1)
        db.commit()
        db.refresh(o1)

        item1 = OrderItem(
            order_id=o1.id,
            product_id=p1.id,
            quantity=3,
            unit_price=Decimal("500.00"),
            total_amount=Decimal("1500.00"),
        )
        db.add(item1)

        # Store 2: 1 order of 2500.00 today
        o2 = Order(
            tenant_id=tenant1_id,
            store_id=store2_id,
            customer_id=customer.id,
            order_number=f"ORD-S2-{suffix}",
            order_type="pos",
            status="completed",
            subtotal=Decimal("2500.00"),
            total_amount=Decimal("2500.00"),
            payment_status="paid",
            created_at=now,
        )
        db.add(o2)
        db.commit()
        db.refresh(o2)

        item2 = OrderItem(
            order_id=o2.id,
            product_id=p2.id,
            quantity=2,
            unit_price=Decimal("1000.00"),
            total_amount=Decimal("2000.00"),
        )
        db.add(item2)
        db.commit()

        # 9. Register Tenant 2 & Store B (Cross-Tenant Store)
        t2_suffix = uuid.uuid4().hex[:6]
        t2_owner_email = f"t2_owner_{t2_suffix}@retailtest.com"
        reg_t2 = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"CrossTenant Store {t2_suffix}",
                "domain": f"cross-{t2_suffix}",
                "owner_email": t2_owner_email,
                "owner_name": f"T2 Owner {t2_suffix}",
                "password": "Password123!",
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_t2.status_code == 200
        tenant2_id = reg_t2.json()["tenant_id"]

        login_t2 = client.post(
            "/api/v1/auth/login",
            json={"email": t2_owner_email, "password": "Password123!"},
        )
        assert login_t2.status_code == 200
        t2_headers = {"Authorization": f"Bearer {login_t2.json()['access_token']}"}

        t2_store_res = client.post(
            "/api/v1/stores/",
            headers=t2_headers,
            json={"name": f"Store Tenant 2 {t2_suffix}", "code": f"T2{t2_suffix[:4].upper()}"},
        )
        assert t2_store_res.status_code == 201
        store_tenant2_id = t2_store_res.json()["id"]

        return {
            "tenant1_id": tenant1_id,
            "owner_headers": owner_headers,
            "store1_id": store1_id,
            "store1_name": store1_name,
            "store2_id": store2_id,
            "store2_name": store2_name,
            "staff_headers": staff_headers,
            "staff_user_id": staff_user.id,
            "tenant2_id": tenant2_id,
            "store_tenant2_id": store_tenant2_id,
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def multi_store_data():
    return _setup_multi_store_fixture()


def test_owner_dashboard_all_stores_mode(multi_store_data):
    """
    Owner viewing dashboard without store_id:
    - Mode must be 'all_stores'
    - store_id and store_name must be None
    - stores_summary list populated
    - Sum of today_sales across stores must match consolidated today_sales
    """
    headers = multi_store_data["owner_headers"]
    res = client.get("/api/v1/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == "all_stores"
    assert data["store_id"] is None
    assert data["store_name"] is None
    assert data["stores_summary"] is not None
    assert len(data["stores_summary"]) >= 2

    # Check store summaries
    store_ids_in_summary = [s["store_id"] for s in data["stores_summary"]]
    assert multi_store_data["store1_id"] in store_ids_in_summary
    assert multi_store_data["store2_id"] in store_ids_in_summary

    # Mathematical consistency verification:
    # Store 1 = 1500.0, Store 2 = 2500.0 => Total = 4000.0
    summary_today_total = sum(s["today_sales"] for s in data["stores_summary"])
    assert data["today_sales"] == pytest.approx(summary_today_total, 0.01)
    assert data["today_sales"] >= 4000.0
    assert data["total_revenue"] >= 4000.0

    # Low stock count in consolidated: Store 1 has 1 low stock product
    assert data["low_stock_products"] >= 1


def test_owner_dashboard_single_store_drilldown_store1(multi_store_data):
    """
    Owner drilling down into Store 1:
    - Mode must be 'single_store'
    - store_id must match Store 1
    - store_name must match Store 1 name
    - stores_summary must be None
    - today_sales must reflect Store 1 only (1500.0)
    - low_stock_products must reflect Store 1 only (1)
    """
    headers = multi_store_data["owner_headers"]
    store1_id = multi_store_data["store1_id"]
    res = client.get(f"/api/v1/dashboard?store_id={store1_id}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == "single_store"
    assert data["store_id"] == store1_id
    assert data["store_name"] == multi_store_data["store1_name"]
    assert data["stores_summary"] is None
    assert data["today_sales"] == pytest.approx(1500.0, 0.01)
    assert data["total_revenue"] == pytest.approx(1500.0, 0.01)
    assert data["low_stock_products"] == 1


def test_owner_dashboard_single_store_drilldown_store2(multi_store_data):
    """
    Owner drilling down into Store 2:
    - Mode must be 'single_store'
    - store_id must match Store 2
    - store_name must match Store 2 name
    - stores_summary must be None
    - today_sales must reflect Store 2 only (2500.0)
    - low_stock_products must reflect Store 2 only (0)
    """
    headers = multi_store_data["owner_headers"]
    store2_id = multi_store_data["store2_id"]
    res = client.get(f"/api/v1/dashboard?store_id={store2_id}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == "single_store"
    assert data["store_id"] == store2_id
    assert data["store_name"] == multi_store_data["store2_name"]
    assert data["stores_summary"] is None
    assert data["today_sales"] == pytest.approx(2500.0, 0.01)
    assert data["total_revenue"] == pytest.approx(2500.0, 0.01)
    assert data["low_stock_products"] == 0


def test_owner_dashboard_nonexistent_store_404(multi_store_data):
    """
    Owner requesting a store ID that does not exist must receive 404 Not Found.
    """
    headers = multi_store_data["owner_headers"]
    res = client.get("/api/v1/dashboard?store_id=999999", headers=headers)
    assert res.status_code == 404, res.text
    body = res.json()
    assert "not found" in body.get("message", "").lower()


def test_owner_dashboard_cross_tenant_store_404(multi_store_data):
    """
    Owner of Tenant 1 requesting a store belonging to Tenant 2 must receive 404 Not Found.
    Strict tenant isolation - no 403, no leakage that store exists in another tenant.
    """
    headers = multi_store_data["owner_headers"]
    cross_store_id = multi_store_data["store_tenant2_id"]
    res = client.get(f"/api/v1/dashboard?store_id={cross_store_id}", headers=headers)
    assert res.status_code == 404, res.text
    body = res.json()
    assert "not found" in body.get("message", "").lower()


def test_store_staff_omitted_store_id_auto_locked_to_assigned_store(multi_store_data):
    """
    Store 1 staff omitting store_id parameter:
    - Must automatically lock to their own store (Store 1)
    - Mode must be 'single_store'
    - store_id must be Store 1
    """
    headers = multi_store_data["staff_headers"]
    res = client.get("/api/v1/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == "single_store"
    assert data["store_id"] == multi_store_data["store1_id"]
    assert data["store_name"] == multi_store_data["store1_name"]
    assert data["today_sales"] == pytest.approx(1500.0, 0.01)


def test_store_staff_matching_store_id_allowed(multi_store_data):
    """
    Store 1 staff explicitly passing store_id=Store 1:
    - Must be allowed (200 OK)
    - Returns Store 1 metrics
    """
    headers = multi_store_data["staff_headers"]
    store1_id = multi_store_data["store1_id"]
    res = client.get(f"/api/v1/dashboard?store_id={store1_id}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == "single_store"
    assert data["store_id"] == store1_id


def test_store_staff_different_store_id_forbidden_403(multi_store_data):
    """
    Store 1 staff requesting Store 2 must receive 403 Forbidden.
    Store boundaries strictly enforced.
    """
    headers = multi_store_data["staff_headers"]
    store2_id = multi_store_data["store2_id"]
    res = client.get(f"/api/v1/dashboard?store_id={store2_id}", headers=headers)
    assert res.status_code == 403, res.text
    body = res.json()
    assert "not authorized" in body.get("message", "").lower() or "forbidden" in body.get("message", "").lower()


def test_store_staff_arbitrary_store_id_forbidden_403(multi_store_data):
    """
    Store 1 staff attempting to request non-existent or arbitrary store ID:
    Must receive 403 Forbidden because staff are not authorized to query other stores.
    """
    headers = multi_store_data["staff_headers"]
    res = client.get("/api/v1/dashboard?store_id=999999", headers=headers)
    assert res.status_code == 403, res.text


def test_sub_endpoints_store_filtering(multi_store_data):
    """
    Verify /overview, /revenue-vs-cost, and /top-products support store_id:
    - 200 OK with valid store_id
    - 404 with cross-tenant or invalid store_id
    - 403 when store staff accesses another store
    """
    headers = multi_store_data["owner_headers"]
    store1_id = multi_store_data["store1_id"]
    cross_store_id = multi_store_data["store_tenant2_id"]
    staff_headers = multi_store_data["staff_headers"]
    store2_id = multi_store_data["store2_id"]

    # 1. Overview
    res_ov = client.get(f"/api/v1/dashboard/overview?store_id={store1_id}", headers=headers)
    assert res_ov.status_code == 200, res_ov.text
    assert "overview" in res_ov.json()
    assert len(res_ov.json()["overview"]) == 12

    # Overview cross-tenant -> 404
    assert client.get(f"/api/v1/dashboard/overview?store_id={cross_store_id}", headers=headers).status_code == 404

    # Overview staff accessing store 2 -> 403
    assert client.get(f"/api/v1/dashboard/overview?store_id={store2_id}", headers=staff_headers).status_code == 403

    # 2. Revenue vs Cost
    res_rc = client.get(f"/api/v1/dashboard/revenue-vs-cost?store_id={store1_id}", headers=headers)
    assert res_rc.status_code == 200, res_rc.text
    assert res_rc.json()["revenue"] == pytest.approx(1500.0, 0.01)

    # Revenue vs Cost cross-tenant -> 404
    assert client.get(f"/api/v1/dashboard/revenue-vs-cost?store_id={cross_store_id}", headers=headers).status_code == 404

    # Revenue vs Cost staff accessing store 2 -> 403
    assert client.get(f"/api/v1/dashboard/revenue-vs-cost?store_id={store2_id}", headers=staff_headers).status_code == 403

    # 3. Top Products
    res_tp = client.get(f"/api/v1/dashboard/top-products?store_id={store1_id}", headers=headers)
    assert res_tp.status_code == 200, res_tp.text
    assert "top_products" in res_tp.json()
    assert len(res_tp.json()["top_products"]) >= 1
    assert res_tp.json()["top_products"][0]["revenue"] == pytest.approx(1500.0, 0.01)

    # Top Products cross-tenant -> 404
    assert client.get(f"/api/v1/dashboard/top-products?store_id={cross_store_id}", headers=headers).status_code == 404

    # Top Products staff accessing store 2 -> 403
    assert client.get(f"/api/v1/dashboard/top-products?store_id={store2_id}", headers=staff_headers).status_code == 403


def test_dashboard_store_id_validation_errors(multi_store_data):
    """
    Validation error testing:
    - store_id = 0 -> 422
    - store_id = -1 -> 422
    - store_id = 'invalid' -> 422
    Sub-endpoints also return 422 for store_id <= 0
    """
    headers = multi_store_data["owner_headers"]
    assert client.get("/api/v1/dashboard?store_id=0", headers=headers).status_code == 422
    assert client.get("/api/v1/dashboard?store_id=-5", headers=headers).status_code == 422
    assert client.get("/api/v1/dashboard?store_id=abc", headers=headers).status_code == 422
    assert client.get("/api/v1/dashboard/overview?store_id=0", headers=headers).status_code == 422
    assert client.get("/api/v1/dashboard/revenue-vs-cost?store_id=-1", headers=headers).status_code == 422
    assert client.get("/api/v1/dashboard/top-products?store_id=0", headers=headers).status_code == 422


def test_empty_tenant_zero_stores():
    """
    Tenant with zero stores created:
    - Must return 200 OK
    - metrics all 0.0
    - stores_summary == []
    """
    suffix = uuid.uuid4().hex[:6]
    owner_email = f"empty_{suffix}@retailtest.com"
    owner_pass = "OwnerPass123!"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Empty Retail {suffix}",
            "domain": f"empty-{suffix}",
            "owner_email": owner_email,
            "owner_name": f"Owner {suffix}",
            "password": owner_pass,
            "owner_phone": _gen_phone(),
            "plan_code": "enterprise",
        },
    )
    assert reg_res.status_code == 200
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": owner_pass},
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    res = client.get("/api/v1/dashboard", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "all_stores"
    assert data["today_sales"] == 0.0
    assert data["monthly_sales"] == 0.0
    assert data["total_revenue"] == 0.0
    assert data["total_customers"] == 0
    assert data["low_stock_products"] == 0
    assert data["stores_summary"] == []


def test_store_with_zero_orders_and_zero_inventory(multi_store_data):
    """
    Drilldown into a store with zero orders, zero customers, and zero inventory:
    - Must return 200 OK with all 0s
    - stores_summary must be None
    """
    headers = multi_store_data["owner_headers"]
    suffix = uuid.uuid4().hex[:6]
    s3_res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={"name": f"Zero Store {suffix}", "code": f"Z0{suffix[:4].upper()}"},
    )
    assert s3_res.status_code == 201
    store3_id = s3_res.json()["id"]

    res = client.get(f"/api/v1/dashboard?store_id={store3_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "single_store"
    assert data["store_id"] == store3_id
    assert data["today_sales"] == 0.0
    assert data["monthly_sales"] == 0.0
    assert data["total_customers"] == 0
    assert data["total_revenue"] == 0.0
    assert data["low_stock_products"] == 0
    assert data["stores_summary"] is None

    # Sub-endpoints should also handle zero data cleanly
    res_ov = client.get(f"/api/v1/dashboard/overview?store_id={store3_id}", headers=headers)
    assert res_ov.status_code == 200
    assert all(m["sales"] == 0.0 for m in res_ov.json()["overview"])

    res_rc = client.get(f"/api/v1/dashboard/revenue-vs-cost?store_id={store3_id}", headers=headers)
    assert res_rc.status_code == 200
    assert res_rc.json()["revenue"] == 0.0
    assert res_rc.json()["cost"] == 0.0

    res_tp = client.get(f"/api/v1/dashboard/top-products?store_id={store3_id}", headers=headers)
    assert res_tp.status_code == 200
    assert res_tp.json()["top_products"] == []


def test_inactive_store_behavior(multi_store_data):
    """
    Inactive store:
    - Included in stores_summary with is_active=False
    - Owner can still view historical metrics via drilldown
    """
    headers = multi_store_data["owner_headers"]
    suffix = uuid.uuid4().hex[:6]
    s_res = client.post(
        "/api/v1/stores/",
        headers=headers,
        json={"name": f"Inactive Store {suffix}", "code": f"IN{suffix[:4].upper()}"},
    )
    assert s_res.status_code == 201
    store_id = s_res.json()["id"]

    # Deactivate the store
    patch_res = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False

    # All stores dashboard should list it with is_active = False
    dash_res = client.get("/api/v1/dashboard", headers=headers)
    assert dash_res.status_code == 200
    item = next((s for s in dash_res.json()["stores_summary"] if s["store_id"] == store_id), None)
    assert item is not None
    assert item["is_active"] is False

    # Owner can still drill down
    drill_res = client.get(f"/api/v1/dashboard?store_id={store_id}", headers=headers)
    assert drill_res.status_code == 200
    assert drill_res.json()["mode"] == "single_store"


def test_cashier_role_forbidden_from_dashboard(multi_store_data):
    """
    Cashier user without dashboard:view permission must be rejected with 403 Forbidden.
    """
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]
    tenant_id = multi_store_data["tenant1_id"]
    try:
        cashier_role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant_id, Role.name == "cashier")
            .first()
        )
        if not cashier_role:
            cashier_role = Role(
                tenant_id=tenant_id,
                name="cashier",
                is_system=False,
                permissions=["billing:read", "billing:write", "orders:read"],
            )
            db.add(cashier_role)
            db.commit()
            db.refresh(cashier_role)

        cashier_email = f"cashier_{suffix}@retailtest.com"
        cashier_pass = "CashierPass123!"
        cashier_user = User(
            tenant_id=tenant_id,
            store_id=multi_store_data["store1_id"],
            role_id=cashier_role.id,
            email=cashier_email,
            password_hash=get_password_hash(cashier_pass),
            full_name=f"Cashier {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(cashier_user)
        db.commit()

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": cashier_email, "password": cashier_pass},
        )
        assert login_res.status_code == 200
        cashier_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Attempt dashboard access
        res = client.get("/api/v1/dashboard", headers=cashier_headers)
        assert res.status_code == 403, res.text
        assert "permission" in res.json().get("message", "").lower()

        # Attempt sub-endpoint access
        res_ov = client.get("/api/v1/dashboard/overview", headers=cashier_headers)
        assert res_ov.status_code == 403, res_ov.text
    finally:
        db.close()

