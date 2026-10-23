from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.store_expense import StoreExpense

client = TestClient(app)


def create_tenant_client(prefix: str):
    """Helper to register and login a distinct tenant."""
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
def setup_data():
    tenant = create_tenant_client("adv-exp")
    db = SessionLocal()
    try:
        s1 = Store(name="Main Superstore", code=f"MS-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=True)
        s2 = Store(name="Express Branch", code=f"EB-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=True)
        s_inactive = Store(name="Closed Branch", code=f"CB-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=False)
        db.add_all([s1, s2, s_inactive])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        db.refresh(s_inactive)
        return {
            "tenant": tenant,
            "store1": s1,
            "store2": s2,
            "inactive_store": s_inactive,
        }
    finally:
        db.close()


def test_create_expense_with_inactive_store_rejected(setup_data):
    tenant = setup_data["tenant"]
    inactive_store = setup_data["inactive_store"]

    payload = {
        "store_id": inactive_store.id,
        "amount": 250.00,
        "category": "Maintenance",
        "description": "Repairs for closed store",
        "expense_date": str(date.today()),
        "payment_method": "cash",
    }
    resp = client.post(
        "/api/v1/store-expenses",
        json=payload,
        headers=tenant["headers"],
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


def test_create_and_read_expense_has_rich_details(setup_data):
    tenant = setup_data["tenant"]
    store1 = setup_data["store1"]

    payload = {
        "store_id": store1.id,
        "amount": 500.50,
        "category": "Rent",
        "description": "Store monthly rent",
        "expense_date": str(date.today()),
        "payment_method": "bank_transfer",
    }
    resp = client.post(
        "/api/v1/store-expenses",
        json=payload,
        headers=tenant["headers"],
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["amount"] == "500.50"
    assert data["category"] == "Rent"
    assert data["store_name"] == store1.name
    assert data["status"] == "active"
    assert data["created_by_name"] is not None


def test_list_expenses_tenant_wide_and_filters(setup_data):
    tenant = setup_data["tenant"]
    store1 = setup_data["store1"]
    store2 = setup_data["store2"]

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Create expenses across both stores
    exp1 = {
        "store_id": store1.id,
        "amount": 100.00,
        "category": "Utilities",
        "description": "Electricity",
        "expense_date": str(today),
        "payment_method": "cash",
    }
    exp2 = {
        "store_id": store2.id,
        "amount": 200.00,
        "category": "Salary",
        "description": "Staff advance",
        "expense_date": str(yesterday),
        "payment_method": "upi",
    }
    exp3 = {
        "store_id": store1.id,
        "amount": 300.00,
        "category": "Utilities",
        "description": "Water bill",
        "expense_date": str(yesterday),
        "payment_method": "card",
    }

    client.post("/api/v1/store-expenses", json=exp1, headers=tenant["headers"])
    client.post("/api/v1/store-expenses", json=exp2, headers=tenant["headers"])
    client.post("/api/v1/store-expenses", json=exp3, headers=tenant["headers"])

    # 1. Tenant-wide without store_id
    resp = client.get("/api/v1/store-expenses", headers=tenant["headers"])
    assert resp.status_code == 200
    all_items = resp.json()
    assert len(all_items) >= 3

    # 2. Filter by store_id
    resp_s1 = client.get(f"/api/v1/store-expenses?store_id={store1.id}", headers=tenant["headers"])
    assert resp_s1.status_code == 200
    s1_items = resp_s1.json()
    assert all(item["store_id"] == store1.id for item in s1_items)

    # 3. Filter by category
    resp_cat = client.get("/api/v1/store-expenses?category=Utilities", headers=tenant["headers"])
    assert resp_cat.status_code == 200
    cat_items = resp_cat.json()
    assert all(item["category"] == "Utilities" for item in cat_items)
    assert len(cat_items) >= 2

    # 4. Filter by payment_method
    resp_pm = client.get("/api/v1/store-expenses?payment_method=upi", headers=tenant["headers"])
    assert resp_pm.status_code == 200
    pm_items = resp_pm.json()
    assert all(item["payment_method"] == "upi" for item in pm_items)

    # 5. Filter by date range
    resp_date = client.get(f"/api/v1/store-expenses?start_date={yesterday}&end_date={yesterday}", headers=tenant["headers"])
    assert resp_date.status_code == 200
    date_items = resp_date.json()
    assert all(item["expense_date"] == str(yesterday) for item in date_items)

    # 6. Pagination skip and limit
    resp_pag = client.get("/api/v1/store-expenses?limit=1&skip=0", headers=tenant["headers"])
    assert resp_pag.status_code == 200
    assert len(resp_pag.json()) == 1


def test_analytics_summary_endpoint(setup_data):
    tenant = setup_data["tenant"]
    store1 = setup_data["store1"]
    store2 = setup_data["store2"]

    today = date.today()

    # Seed expenses:
    # store1: 1000 cash Rent
    # store1: 500 upi Utilities
    # store2: 1500 card Salary
    client.post("/api/v1/store-expenses", json={
        "store_id": store1.id,
        "amount": 1000.00,
        "category": "Rent",
        "expense_date": str(today),
        "payment_method": "cash",
    }, headers=tenant["headers"])

    client.post("/api/v1/store-expenses", json={
        "store_id": store1.id,
        "amount": 500.00,
        "category": "Utilities",
        "expense_date": str(today),
        "payment_method": "upi",
    }, headers=tenant["headers"])

    client.post("/api/v1/store-expenses", json={
        "store_id": store2.id,
        "amount": 1500.00,
        "category": "Salary",
        "expense_date": str(today),
        "payment_method": "card",
    }, headers=tenant["headers"])

    # Global summary
    resp = client.get("/api/v1/store-expenses/summary", headers=tenant["headers"])
    assert resp.status_code == 200, resp.text
    summary = resp.json()

    assert summary["total_expenses"] == "3000.00"
    assert summary["total_count"] == 3
    assert summary["cash_expenses"] == "1000.00"
    assert summary["digital_expenses"] == "2000.00"

    # Category breakdown
    cats = {c["category"]: c for c in summary["categories_breakdown"]}
    assert "Salary" in cats
    assert cats["Salary"]["total_amount"] == "1500.00"
    assert cats["Salary"]["percentage"] == 50.0

    # Payment method breakdown
    pms = {p["payment_method"]: p for p in summary["payment_methods_breakdown"]}
    assert "cash" in pms
    assert pms["cash"]["total_amount"] == "1000.00"

    # Store comparison
    stores_comp = {s["store_id"]: s for s in summary["store_comparison"]}
    assert store1.id in stores_comp
    assert stores_comp[store1.id]["total_amount"] == "1500.00"
    assert stores_comp[store2.id]["total_amount"] == "1500.00"

    # Filter summary by store_id
    resp_s1 = client.get(f"/api/v1/store-expenses/summary?store_id={store1.id}", headers=tenant["headers"])
    assert resp_s1.status_code == 200
    s1_sum = resp_s1.json()
    assert s1_sum["total_expenses"] == "1500.00"
    assert s1_sum["total_count"] == 2

    # Invalid date range
    resp_err = client.get(
        f"/api/v1/store-expenses/summary?start_date={today}&end_date={today - timedelta(days=1)}",
        headers=tenant["headers"],
    )
    assert resp_err.status_code == 400


def test_daily_report_endpoint(setup_data):
    tenant = setup_data["tenant"]
    store1 = setup_data["store1"]

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Day 1 (today) store1:
    # 300 cash (drawer payout)
    # 150 cash (drawer payout)
    # 400 card (non-cash)
    client.post("/api/v1/store-expenses", json={
        "store_id": store1.id,
        "amount": 300.00,
        "category": "Office Supplies",
        "description": "Stationery cash purchase",
        "expense_date": str(today),
        "payment_method": "cash",
    }, headers=tenant["headers"])

    client.post("/api/v1/store-expenses", json={
        "store_id": store1.id,
        "amount": 150.00,
        "category": "Travel",
        "description": "Auto fare cash",
        "expense_date": str(today),
        "payment_method": "cash",
    }, headers=tenant["headers"])

    client.post("/api/v1/store-expenses", json={
        "store_id": store1.id,
        "amount": 400.00,
        "category": "Maintenance",
        "description": "AC filter card payment",
        "expense_date": str(today),
        "payment_method": "card",
    }, headers=tenant["headers"])

    # Yesterday expense (should not appear in today's report)
    client.post("/api/v1/store-expenses", json={
        "store_id": store1.id,
        "amount": 999.00,
        "category": "Rent",
        "expense_date": str(yesterday),
        "payment_method": "cash",
    }, headers=tenant["headers"])

    # Call daily report for store1 today
    resp = client.get(
        f"/api/v1/store-expenses/daily-report?store_id={store1.id}&report_date={today}",
        headers=tenant["headers"],
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["report_date"] == str(today)
    assert report["store_id"] == store1.id
    assert report["store_name"] == store1.name
    assert report["total_expenses"] == "850.00"
    assert report["total_count"] == 3
    assert report["cash_expense_total"] == "450.00"
    assert report["non_cash_expense_total"] == "400.00"
    assert report["cash_drawer_payout_count"] == 2
    assert len(report["expenses"]) == 3

    # Check default date (omit report_date, defaults to today)
    resp_default = client.get(
        f"/api/v1/store-expenses/daily-report?store_id={store1.id}",
        headers=tenant["headers"],
    )
    assert resp_default.status_code == 200
    assert resp_default.json()["total_expenses"] == "850.00"

    # Non-existent store gives 404
    resp_404 = client.get(
        "/api/v1/store-expenses/daily-report?store_id=999999",
        headers=tenant["headers"],
    )
    assert resp_404.status_code == 404
