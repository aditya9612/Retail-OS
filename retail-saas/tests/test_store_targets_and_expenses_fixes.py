import uuid
from datetime import datetime, date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.store_target import StoreTargetCreate

client = TestClient(app)


def create_tenant_and_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {slug}",
            "domain": slug,
            "owner_email": email,
            "owner_name": f"Admin {prefix}",
            "password": "Password123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

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
    }


def create_store(headers: dict, name: str = "Test Store Branch"):
    store_code = f"STR-{uuid.uuid4().hex[:4].upper()}"
    store_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": name,
            "code": store_code,
            "address": "123 High Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "phone": "9876543210",
        },
        headers=headers,
    )
    assert store_resp.status_code == 201, store_resp.text
    return store_resp.json()


# ==============================================================================
# Issue 1: Store Targets â€” Monthly date range
# ==============================================================================

def test_monthly_target_uses_complete_calendar_month():
    tenant = create_tenant_and_admin("monthly-date")
    store = create_store(tenant["headers"], "Month Branch")

    # 1. February in a leap year (2024 -> 29 days)
    resp_leap = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales",
            "target_value": 50000.00,
            "period": "monthly",
            "start_date": "2024-02-15T10:30:00",
            "end_date": "2024-02-20T18:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_leap.status_code == 201, resp_leap.text
    data_leap = resp_leap.json()
    assert data_leap["start_date"].startswith("2024-02-01T00:00:00")
    assert data_leap["end_date"].startswith("2024-02-29T23:59:59")

    # 2. February in a non-leap year (2025 -> 28 days)
    resp_non_leap = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales",
            "target_value": 45000.00,
            "period": "monthly",
            "start_date": "2025-02-10T09:00:00",
            "end_date": "2025-02-18T17:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_non_leap.status_code == 201, resp_non_leap.text
    data_non_leap = resp_non_leap.json()
    assert data_non_leap["start_date"].startswith("2025-02-01T00:00:00")
    assert data_non_leap["end_date"].startswith("2025-02-28T23:59:59")

    # 3. 30-day month (April 2026 -> 30 days)
    resp_30 = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales",
            "target_value": 60000.00,
            "period": "monthly",
            "start_date": "2026-04-12T00:00:00",
            "end_date": "2026-04-20T00:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_30.status_code == 201, resp_30.text
    data_30 = resp_30.json()
    assert data_30["start_date"].startswith("2026-04-01T00:00:00")
    assert data_30["end_date"].startswith("2026-04-30T23:59:59")

    # 4. 31-day month (October 2026 -> 31 days)
    resp_31 = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales",
            "target_value": 70000.00,
            "period": "monthly",
            "start_date": "2026-10-05T08:00:00",
            "end_date": "2026-10-25T20:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_31.status_code == 201, resp_31.text
    data_31 = resp_31.json()
    assert data_31["start_date"].startswith("2026-10-01T00:00:00")
    assert data_31["end_date"].startswith("2026-10-31T23:59:59")


# ==============================================================================
# Issue 2: Store Targets â€” Invalid target_type accepted
# ==============================================================================

def test_invalid_target_type_rejected():
    tenant = create_tenant_and_admin("ttype-val")
    store = create_store(tenant["headers"], "Type Branch")

    # 1. Invalid target_type "no" -> Must be rejected with 422
    resp_no = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "no",
            "target_value": 10000.00,
            "period": "monthly",
            "start_date": "2026-10-01T00:00:00",
            "end_date": "2026-10-31T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert resp_no.status_code == 422, resp_no.text

    # 2. Other invalid target_types: "yes", "abc", "random" -> 422
    for bad_ttype in ["yes", "abc", "random"]:
        resp_bad = client.post(
            "/api/v1/store-targets",
            json={
                "store_id": store["id"],
                "target_type": bad_ttype,
                "target_value": 10000.00,
                "period": "monthly",
                "start_date": "2026-10-01T00:00:00",
                "end_date": "2026-10-31T23:59:59",
            },
            headers=tenant["headers"],
        )
        assert resp_bad.status_code == 422, f"Allowed bad target_type: {bad_ttype}"

    # 3. Valid supported target types -> 201
    resp_ok = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales",
            "target_value": 10000.00,
            "period": "monthly",
            "start_date": "2026-10-01T00:00:00",
            "end_date": "2026-10-31T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert resp_ok.status_code == 201, resp_ok.text


# ==============================================================================
# Issue 3: Store Targets â€” target_value returned as a number
# ==============================================================================

def test_store_target_value_returned_as_number():
    tenant = create_tenant_and_admin("tval-num")
    store = create_store(tenant["headers"], "Num Branch")

    resp = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Revenue",
            "target_value": 12345.67,
            "period": "monthly",
            "start_date": "2026-10-01T00:00:00",
            "end_date": "2026-10-31T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Must be JSON number, not quoted string
    assert isinstance(data["target_value"], (int, float)), f"target_value is not numeric: {type(data['target_value'])}"
    assert not isinstance(data["target_value"], str), "target_value is a quoted string"
    assert data["target_value"] == 12345.67


# ==============================================================================
# Issue 4: Store Expenses â€” amount returned as a number
# ==============================================================================

def test_store_expense_amount_returned_as_number():
    tenant = create_tenant_and_admin("exp-num")
    store = create_store(tenant["headers"], "Expense Branch")

    today = date.today().isoformat()
    ref_num = f"EXP-{uuid.uuid4().hex[:4].upper()}-{date.today().strftime('%Y%m%d')}"
    resp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": store["id"],
            "amount": 2450.75,
            "category": "Rent",
            "description": "Monthly branch rent",
            "expense_date": today,
            "payment_method": "bank_transfer",
            "reference_number": ref_num,
        },
        headers=tenant["headers"],
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Must be JSON number, not quoted string
    assert isinstance(data["amount"], (int, float)), f"amount is not numeric: {type(data['amount'])}"
    assert not isinstance(data["amount"], str), "amount is a quoted string"
    assert data["amount"] == 2450.75


# ==============================================================================
# Date Range Computation for All Supported Periods (daily, weekly, quarterly, yearly)
# ==============================================================================

def test_daily_weekly_quarterly_yearly_date_computation():
    tenant = create_tenant_and_admin("period-dates")
    store = create_store(tenant["headers"], "Period Dates Branch")

    # 1. Daily: 2026-05-15 14:30:00 -> 2026-05-15 00:00:00 to 2026-05-15 23:59:59
    resp_daily = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Daily Sales",
            "target_value": 5000.00,
            "period": "daily",
            "start_date": "2026-05-15T14:30:00",
            "end_date": "2026-05-15T18:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_daily.status_code == 201, resp_daily.text
    d_daily = resp_daily.json()
    assert d_daily["start_date"].startswith("2026-05-15T00:00:00")
    assert d_daily["end_date"].startswith("2026-05-15T23:59:59")

    # 2. Weekly: 2026-10-28 (Wednesday) -> Monday 2026-10-26 00:00:00 to Sunday 2026-11-01 23:59:59
    resp_weekly = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Weekly Sales",
            "target_value": 25000.00,
            "period": "weekly",
            "start_date": "2026-10-28T10:00:00",
            "end_date": "2026-10-29T12:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_weekly.status_code == 201, resp_weekly.text
    d_weekly = resp_weekly.json()
    assert d_weekly["start_date"].startswith("2026-10-26T00:00:00")
    assert d_weekly["end_date"].startswith("2026-11-01T23:59:59")

    # 3. Quarterly: 2026-02-10 (Q1) -> Jan 1 to Mar 31 23:59:59
    resp_q1 = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Quarterly Sales",
            "target_value": 150000.00,
            "period": "quarterly",
            "start_date": "2026-02-10T12:00:00",
            "end_date": "2026-02-28T12:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_q1.status_code == 201, resp_q1.text
    d_q1 = resp_q1.json()
    assert d_q1["start_date"].startswith("2026-01-01T00:00:00")
    assert d_q1["end_date"].startswith("2026-03-31T23:59:59")

    # 4. 15 Days: 2026-06-01 -> 2026-06-01 00:00:00 to 2026-06-15 23:59:59
    resp_15 = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Orders Target",
            "target_value": 1000.00,
            "period": "15_days",
            "start_date": "2026-06-01T12:00:00",
            "end_date": "2026-06-10T12:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_15.status_code == 201, resp_15.text
    d_15 = resp_15.json()
    assert d_15["start_date"].startswith("2026-06-01T00:00:00")
    assert d_15["end_date"].startswith("2026-06-15T23:59:59")
    assert d_15["period"] == "15_days"

    # Also test "15 days" space format acceptance and normalization
    resp_15_space = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Orders Target",
            "target_value": 1200.00,
            "period": "15 days",
            "start_date": "2026-06-16T10:00:00",
            "end_date": "2026-06-25T10:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_15_space.status_code == 201, resp_15_space.text
    d_15_space = resp_15_space.json()
    assert d_15_space["start_date"].startswith("2026-06-16T00:00:00")
    assert d_15_space["end_date"].startswith("2026-06-30T23:59:59")
    assert d_15_space["period"] == "15_days"

    # 5. Yearly: 2026-07-04 -> Jan 1 00:00:00 to Dec 31 23:59:59
    resp_yearly = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Yearly Sales",
            "target_value": 600000.00,
            "period": "yearly",
            "start_date": "2026-07-04T08:00:00",
            "end_date": "2026-07-05T08:00:00",
        },
        headers=tenant["headers"],
    )
    assert resp_yearly.status_code == 201, resp_yearly.text
    d_yearly = resp_yearly.json()
    assert d_yearly["start_date"].startswith("2026-01-01T00:00:00")
    assert d_yearly["end_date"].startswith("2026-12-31T23:59:59")


# ==============================================================================
# Period Filter & Validation Rejection Messages
# ==============================================================================

def test_period_filter_and_rejection_validation_messages():
    tenant = create_tenant_and_admin("period-filt")
    store = create_store(tenant["headers"], "Period Filter Branch")

    # Create daily, 15_days, and monthly targets
    r_daily = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales Target",
            "target_value": 1000.00,
            "period": "daily",
            "start_date": "2026-04-10T00:00:00",
            "end_date": "2026-04-10T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert r_daily.status_code == 201, r_daily.text

    r_15 = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales Target",
            "target_value": 15000.00,
            "period": "15_days",
            "start_date": "2026-04-11T00:00:00",
            "end_date": "2026-04-25T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert r_15.status_code == 201, r_15.text

    r_monthly = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales Target",
            "target_value": 30000.00,
            "period": "monthly",
            "start_date": "2026-05-01T00:00:00",
            "end_date": "2026-05-31T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert r_monthly.status_code == 201, r_monthly.text

    # 1. Filter by period=all returns all targets
    res_all = client.get(f"/api/v1/store-targets?store_id={store['id']}&period=all", headers=tenant["headers"])
    assert res_all.status_code == 200, res_all.text
    periods = [t["period"] for t in res_all.json()]
    assert "daily" in periods
    assert "15_days" in periods
    assert "monthly" in periods

    # 2. Filter by period=daily returns only daily targets
    res_daily_filt = client.get(f"/api/v1/store-targets?store_id={store['id']}&period=daily", headers=tenant["headers"])
    assert res_daily_filt.status_code == 200, res_daily_filt.text
    assert all(t["period"] == "daily" for t in res_daily_filt.json())

    # 3. Filter by period=15_days returns only 15_days targets
    res_15_filt = client.get(f"/api/v1/store-targets?store_id={store['id']}&period=15_days", headers=tenant["headers"])
    assert res_15_filt.status_code == 200, res_15_filt.text
    assert all(t["period"] == "15_days" for t in res_15_filt.json())

    # 4. Invalid period filter on GET /api/v1/store-targets -> 422 with rejection message
    res_invalid_filt = client.get(f"/api/v1/store-targets?period=century", headers=tenant["headers"])
    assert res_invalid_filt.status_code == 422, res_invalid_filt.text
    assert "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly" in res_invalid_filt.text

    # 5. Invalid period filter on GET /api/v1/store-targets/leaderboard -> 422
    res_lb_invalid = client.get("/api/v1/store-targets/leaderboard?period=biweekly", headers=tenant["headers"])
    assert res_lb_invalid.status_code == 422, res_lb_invalid.text
    assert "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly" in res_lb_invalid.text

    # 6. Invalid period filter on GET /api/v1/store-targets/summary -> 422
    res_sum_invalid = client.get("/api/v1/store-targets/summary?period=decade", headers=tenant["headers"])
    assert res_sum_invalid.status_code == 422, res_sum_invalid.text
    assert "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly" in res_sum_invalid.text

    # 7. Invalid period in POST /api/v1/store-targets body -> 422 with rejection message
    res_body_invalid = client.post(
        "/api/v1/store-targets",
        json={
            "store_id": store["id"],
            "target_type": "Sales",
            "target_value": 1000.00,
            "period": "century",
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-01-31T23:59:59",
        },
        headers=tenant["headers"],
    )
    assert res_body_invalid.status_code == 422, res_body_invalid.text
    assert "Period must be one of: all, daily, weekly, 15_days, monthly, quarterly, yearly" in res_body_invalid.text
