import random
import uuid
from decimal import Decimal
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.pos_cash_movement import POSCashMovement
from app.models.pos_shift import POSShift
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.utils.constants import UserRole, PaymentStatus, OrderStatus

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture(scope="module")
def pos_setup():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # 1. Register Tenant 1
        owner_email = f"pos_owner_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"POS Superstore {suffix}",
                "domain": f"pos-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Owner {suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_res.status_code == 200, reg_res.text
        tenant1_id = reg_res.json()["tenant_id"]

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": owner_pass},
        )
        assert login_res.status_code == 200
        owner_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. Create Store 1 & Store 2
        s1 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Store Alpha {suffix}", "code": f"SA{suffix[:4].upper()}"},
        )
        assert s1.status_code == 201
        store1_id = s1.json()["id"]

        s2 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Store Beta {suffix}", "code": f"SB{suffix[:4].upper()}"},
        )
        assert s2.status_code == 201
        store2_id = s2.json()["id"]

        # Ensure Cashier Role
        cashier_role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant1_id, Role.name == "cashier")
            .first()
        )
        if not cashier_role:
            cashier_role = Role(
                tenant_id=tenant1_id,
                name="cashier",
                is_system=False,
                permissions=[
                    "orders:read", "orders:write",
                    "billing:read", "billing:write",
                    "payments:read", "payments:write",
                    "pos:shift_manage",
                ],
            )
            db.add(cashier_role)
            db.commit()
            db.refresh(cashier_role)

        # Ensure Manager Role
        manager_role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant1_id, Role.name == "manager")
            .first()
        )
        if not manager_role:
            manager_role = Role(
                tenant_id=tenant1_id,
                name="manager",
                is_system=False,
                permissions=["stores:read", "users:read", "pos:shift_manage", "billing:read"],
            )
            db.add(manager_role)
            db.commit()
            db.refresh(manager_role)

        # 3. Create Cashier 1 at Store 1
        cashier1_email = f"cashier1_{suffix}@retailtest.com"
        cashier1_pass = "CashierPass123!"
        c1_user = User(
            tenant_id=tenant1_id,
            store_id=store1_id,
            role_id=cashier_role.id,
            email=cashier1_email,
            password_hash=get_password_hash(cashier1_pass),
            full_name=f"Cashier One {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(c1_user)

        # 4. Create Cashier 2 at Store 2
        cashier2_email = f"cashier2_{suffix}@retailtest.com"
        cashier2_pass = "CashierPass123!"
        c2_user = User(
            tenant_id=tenant1_id,
            store_id=store2_id,
            role_id=cashier_role.id,
            email=cashier2_email,
            password_hash=get_password_hash(cashier2_pass),
            full_name=f"Cashier Two {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(c2_user)

        # 5. Create Manager at Store 1
        mgr_email = f"mgr_{suffix}@retailtest.com"
        mgr_pass = "MgrPass123!"
        mgr_user = User(
            tenant_id=tenant1_id,
            store_id=store1_id,
            role_id=manager_role.id,
            email=mgr_email,
            password_hash=get_password_hash(mgr_pass),
            full_name=f"Manager One {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(mgr_user)

        # 6. Create Unassigned User (store_id=None)
        unassigned_email = f"unassigned_{suffix}@retailtest.com"
        unassigned_pass = "UnassignedPass123!"
        unassigned_user = User(
            tenant_id=tenant1_id,
            store_id=None,
            role_id=cashier_role.id,
            email=unassigned_email,
            password_hash=get_password_hash(unassigned_pass),
            full_name=f"Unassigned {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(unassigned_user)

        # 7. Create Accountant (No pos:shift_manage permission)
        accountant_role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant1_id, Role.name == "accountant")
            .first()
        )
        if not accountant_role:
            accountant_role = Role(
                tenant_id=tenant1_id,
                name="accountant",
                is_system=False,
                permissions=["billing:read", "reports:read"],
            )
            db.add(accountant_role)
            db.commit()
            db.refresh(accountant_role)

        acct_email = f"acct_{suffix}@retailtest.com"
        acct_pass = "AcctPass123!"
        acct_user = User(
            tenant_id=tenant1_id,
            store_id=store1_id,
            role_id=accountant_role.id,
            email=acct_email,
            password_hash=get_password_hash(acct_pass),
            full_name=f"Accountant {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(acct_user)

        # 8. Register Tenant 2 for cross-tenant checks
        t2_email = f"t2_{suffix}@retailtest.com"
        t2_pass = "T2Pass123!"
        t2_reg = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Tenant2 POS {suffix}",
                "domain": f"t2pos-{suffix}",
                "owner_email": t2_email,
                "owner_name": f"T2 Owner {suffix}",
                "password": t2_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        tenant2_id = t2_reg.json()["tenant_id"]

        t2_login = client.post(
            "/api/v1/auth/login",
            json={"email": t2_email, "password": t2_pass},
        )
        t2_headers = {"Authorization": f"Bearer {t2_login.json()['access_token']}"}

        db.commit()
        db.refresh(c1_user)
        db.refresh(c2_user)
        db.refresh(mgr_user)
        db.refresh(unassigned_user)
        db.refresh(acct_user)

        # Login tokens
        l1 = client.post("/api/v1/auth/login", json={"email": cashier1_email, "password": cashier1_pass})
        c1_headers = {"Authorization": f"Bearer {l1.json()['access_token']}"}

        l2 = client.post("/api/v1/auth/login", json={"email": cashier2_email, "password": cashier2_pass})
        c2_headers = {"Authorization": f"Bearer {l2.json()['access_token']}"}

        lm = client.post("/api/v1/auth/login", json={"email": mgr_email, "password": mgr_pass})
        mgr_headers = {"Authorization": f"Bearer {lm.json()['access_token']}"}

        lu = client.post("/api/v1/auth/login", json={"email": unassigned_email, "password": unassigned_pass})
        unassigned_headers = {"Authorization": f"Bearer {lu.json()['access_token']}"}

        la = client.post("/api/v1/auth/login", json={"email": acct_email, "password": acct_pass})
        acct_headers = {"Authorization": f"Bearer {la.json()['access_token']}"}

        return {
            "tenant1_id": tenant1_id,
            "tenant2_id": tenant2_id,
            "store1_id": store1_id,
            "store2_id": store2_id,
            "cashier1_id": c1_user.id,
            "cashier2_id": c2_user.id,
            "owner_headers": owner_headers,
            "c1_headers": c1_headers,
            "c2_headers": c2_headers,
            "mgr_headers": mgr_headers,
            "unassigned_headers": unassigned_headers,
            "acct_headers": acct_headers,
            "t2_headers": t2_headers,
        }
    finally:
        db.close()


# ============================================================================
# 1. SHIFT OPEN & VALIDATION TESTS
# ============================================================================

def test_open_shift_success(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={"opening_cash_float": 5000.00, "notes": "Morning cashier shift"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "open"
    assert Decimal(str(data["opening_cash_float"])) == Decimal("5000.00")
    assert data["store_id"] == pos_setup["store1_id"]
    assert data["cashier_id"] == pos_setup["cashier1_id"]
    assert data["closed_at"] is None


def test_open_shift_negative_cash_rejected(pos_setup):
    headers = pos_setup["c2_headers"]
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={"opening_cash_float": -100.00},
    )
    assert res.status_code == 422


def test_open_shift_duplicate_active_shift_rejected(pos_setup):
    # Cashier 1 already opened a shift above
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={"opening_cash_float": 2000.00},
    )
    assert res.status_code in [400, 409]
    assert "already exists" in res.text.lower()


def test_unassigned_user_cannot_open_shift(pos_setup):
    headers = pos_setup["unassigned_headers"]
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={"opening_cash_float": 1000.00},
    )
    assert res.status_code == 400
    assert "assigned to a store" in res.text.lower()


# ============================================================================
# 2. CURRENT SHIFT TESTS
# ============================================================================

def test_get_current_shift_success(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.get("/api/v1/pos/shifts/current", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "open"
    assert data["cashier_id"] == pos_setup["cashier1_id"]


def test_get_current_shift_none_found(pos_setup):
    # Cashier 2 hasn't opened a shift yet
    headers = pos_setup["c2_headers"]
    res = client.get("/api/v1/pos/shifts/current", headers=headers)
    assert res.status_code == 404
    assert "not found" in res.text.lower() or "no active" in res.text.lower()


# ============================================================================
# 3. CASH MOVEMENT TESTS (DROP, PAYOUT, ADDITION)
# ============================================================================

def test_record_cash_drop_success(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_DROP", "amount": 1500.00, "reason": "Mid-day safe drop"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["movement_type"] == "CASH_DROP"
    assert Decimal(str(data["amount"])) == Decimal("1500.00")
    assert data["reason"] == "Mid-day safe drop"


def test_record_cash_payout_success(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_PAYOUT", "amount": 350.00, "reason": "Petty cash for cleaning supply"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["movement_type"] == "CASH_PAYOUT"
    assert Decimal(str(data["amount"])) == Decimal("350.00")


def test_record_cash_addition_success(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_IN", "amount": 500.00, "reason": "Additional coin change added"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["movement_type"] == "CASH_IN"
    assert Decimal(str(data["amount"])) == Decimal("500.00")


def test_record_cash_movement_negative_amount_rejected(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_DROP", "amount": -200.00, "reason": "Invalid drop"},
    )
    assert res.status_code == 422


def test_record_cash_movement_zero_amount_rejected(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_DROP", "amount": 0.00, "reason": "Invalid zero"},
    )
    assert res.status_code == 422


def test_record_cash_movement_empty_reason_rejected(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_DROP", "amount": 500.00, "reason": "   "},
    )
    assert res.status_code == 422


def test_record_cash_movement_without_open_shift_rejected(pos_setup):
    headers = pos_setup["c2_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_DROP", "amount": 500.00, "reason": "Drop without shift"},
    )
    assert res.status_code == 404


# ============================================================================
# 4. CASH SALES & SPLIT-PAYMENT RECONCILIATION
# ============================================================================

def test_expected_cash_with_sales_and_movements(pos_setup):
    """
    Simulate real POS sales:
    - 1 pure cash payment of 1200.00
    - 1 split payment of 800.00 (Cash 500.00 + UPI 300.00)
    Opening float = 5000.00
    Movements:
    - Drop = 1500.00
    - Payout = 350.00
    - Cash in = 500.00
    Cash Sales = 1200 + 500 = 1700.00
    Expected Cash = 5000 + 1700 + 500 - 1500 - 350 = 5350.00
    Counted Cash = 5350.00 -> Variance 0.00 (exact)
    """
    db = SessionLocal()
    tenant_id = pos_setup["tenant1_id"]
    store_id = pos_setup["store1_id"]
    cashier_id = pos_setup["cashier1_id"]

    try:
        # Order 1: Pure Cash
        o1 = Order(
            tenant_id=tenant_id,
            store_id=store_id,
            user_id=cashier_id,
            order_number=f"ORD-CASH-{uuid.uuid4().hex[:6]}",
            order_type="pos",
            status=OrderStatus.CONFIRMED.value,
            total_amount=Decimal("1200.00"),
            payment_status="paid",
        )
        db.add(o1)
        db.flush()

        p1 = Payment(
            tenant_id=tenant_id,
            order_id=o1.id,
            payment_method="cash",
            amount=Decimal("1200.00"),
            status=PaymentStatus.COMPLETED.value,
        )
        db.add(p1)

        # Order 2: Split Payment (500 cash + 300 upi)
        o2 = Order(
            tenant_id=tenant_id,
            store_id=store_id,
            user_id=cashier_id,
            order_number=f"ORD-SPLIT-{uuid.uuid4().hex[:6]}",
            order_type="pos",
            status=OrderStatus.CONFIRMED.value,
            total_amount=Decimal("800.00"),
            payment_status="paid",
        )
        db.add(o2)
        db.flush()

        p2_cash = Payment(
            tenant_id=tenant_id,
            order_id=o2.id,
            payment_method="cash",
            amount=Decimal("500.00"),
            status=PaymentStatus.COMPLETED.value,
        )
        p2_upi = Payment(
            tenant_id=tenant_id,
            order_id=o2.id,
            payment_method="upi",
            amount=Decimal("300.00"),
            status=PaymentStatus.COMPLETED.value,
        )
        db.add(p2_cash)
        db.add(p2_upi)

        # Order 3: Cancelled order (must be excluded)
        o3 = Order(
            tenant_id=tenant_id,
            store_id=store_id,
            user_id=cashier_id,
            order_number=f"ORD-CANC-{uuid.uuid4().hex[:6]}",
            order_type="pos",
            status=OrderStatus.CANCELLED.value,
            total_amount=Decimal("600.00"),
            payment_status="cancelled",
        )
        db.add(o3)
        db.flush()

        p3 = Payment(
            tenant_id=tenant_id,
            order_id=o3.id,
            payment_method="cash",
            amount=Decimal("600.00"),
            status=PaymentStatus.COMPLETED.value,
        )
        db.add(p3)

        db.commit()

        # Close shift with exact counted cash = 5350.00
        headers = pos_setup["c1_headers"]
        res = client.post(
            "/api/v1/pos/shifts/close",
            headers=headers,
            json={"closing_cash_counted": 5350.00, "notes": "Shift 1 end"},
        )
        assert res.status_code == 200, res.text
        data = res.json()

        assert Decimal(str(data["cash_sales"])) == Decimal("1700.00")
        assert Decimal(str(data["cash_drops"])) == Decimal("1500.00")
        assert Decimal(str(data["cash_payouts"])) == Decimal("350.00")
        assert Decimal(str(data["cash_additions"])) == Decimal("500.00")
        assert Decimal(str(data["expected_cash"])) == Decimal("5350.00")
        assert Decimal(str(data["closing_cash_counted"])) == Decimal("5350.00")
        assert Decimal(str(data["cash_variance"])) == Decimal("0.00")
        assert data["variance_status"] == "exact"
        assert data["shift"]["status"] == "closed"
        assert data["shift"]["closed_at"] is not None
    finally:
        db.close()


def test_closed_shift_cannot_be_closed_again(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/close",
        headers=headers,
        json={"closing_cash_counted": 5000.00},
    )
    assert res.status_code == 404
    assert "no active" in res.text.lower()


def test_closed_shift_cannot_receive_movements(pos_setup):
    headers = pos_setup["c1_headers"]
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={"movement_type": "CASH_DROP", "amount": 100.00, "reason": "After close"},
    )
    assert res.status_code == 404


# ============================================================================
# 5. SHIFT SHORTAGE & SURPLUS VARIANCE TESTS
# ============================================================================

def test_close_shift_shortage_variance(pos_setup):
    """
    Open shift with 3000 float.
    Close with 2800 counted.
    Expected = 3000. Variance = -200 (short).
    """
    headers = pos_setup["c2_headers"]
    res_open = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={"opening_cash_float": 3000.00},
    )
    assert res_open.status_code == 201

    res_close = client.post(
        "/api/v1/pos/shifts/close",
        headers=headers,
        json={"closing_cash_counted": 2800.00, "notes": "Shortage test"},
    )
    assert res_close.status_code == 200
    data = res_close.json()
    assert Decimal(str(data["expected_cash"])) == Decimal("3000.00")
    assert Decimal(str(data["closing_cash_counted"])) == Decimal("2800.00")
    assert Decimal(str(data["cash_variance"])) == Decimal("-200.00")
    assert data["variance_status"] == "short"


def test_close_shift_surplus_variance(pos_setup):
    """
    Reopen shift for cashier 2 with 2000 float.
    Close with 2150 counted.
    Expected = 2000. Variance = +150 (over).
    """
    headers = pos_setup["c2_headers"]
    res_open = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={"opening_cash_float": 2000.00},
    )
    assert res_open.status_code == 201
    shift_id = res_open.json()["id"]

    res_close = client.post(
        "/api/v1/pos/shifts/close",
        headers=headers,
        json={"closing_cash_counted": 2150.00, "notes": "Surplus test"},
    )
    assert res_close.status_code == 200
    data = res_close.json()
    assert Decimal(str(data["expected_cash"])) == Decimal("2000.00")
    assert Decimal(str(data["closing_cash_counted"])) == Decimal("2150.00")
    assert Decimal(str(data["cash_variance"])) == Decimal("150.00")
    assert data["variance_status"] == "over"

    # Verify Z-report matches
    res_z = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report", headers=headers)
    assert res_z.status_code == 200
    z_data = res_z.json()
    assert z_data["shift_id"] == shift_id
    assert z_data["variance_status"] == "over"
    assert Decimal(str(z_data["cash_variance"])) == Decimal("150.00")


# ============================================================================
# 6. Z-REPORT AUTHORIZATION & ISOLATION TESTS
# ============================================================================

def test_z_report_comprehensive_metrics(pos_setup):
    headers = pos_setup["c1_headers"]
    # Get cashier 1's closed shift ID
    shifts_res = client.get("/api/v1/pos/shifts", headers=headers)
    assert shifts_res.status_code == 200
    shift_1_id = shifts_res.json()[0]["id"]

    res = client.get(f"/api/v1/pos/shifts/{shift_1_id}/z-report", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["shift_id"] == shift_1_id
    assert data["status"] == "closed"
    assert "Store Alpha" in data["store_name"]
    assert "Cashier One" in data["cashier_name"]
    assert Decimal(str(data["opening_cash_float"])) == Decimal("5000.00")
    assert Decimal(str(data["cash_sales"])) == Decimal("1700.00")
    assert Decimal(str(data["total_sales_amount"])) == Decimal("2000.00")  # 1200 + 800
    assert data["total_transactions"] == 2
    assert "cash" in data["payment_method_breakdown"]
    assert "upi" in data["payment_method_breakdown"]
    assert len(data["movements"]) == 3  # DROP, PAYOUT, IN


def test_cashier_cannot_view_another_cashiers_z_report(pos_setup):
    # Cashier 2 tries to view Cashier 1's shift Z-report
    shifts_res = client.get("/api/v1/pos/shifts", headers=pos_setup["c1_headers"])
    shift_1_id = shifts_res.json()[0]["id"]

    res = client.get(f"/api/v1/pos/shifts/{shift_1_id}/z-report", headers=pos_setup["c2_headers"])
    assert res.status_code == 403
    assert "only view their own" in res.text.lower()


def test_manager_can_view_store_z_report(pos_setup):
    # Manager at Store 1 views Cashier 1's shift at Store 1
    shifts_res = client.get("/api/v1/pos/shifts", headers=pos_setup["c1_headers"])
    shift_1_id = shifts_res.json()[0]["id"]

    res = client.get(f"/api/v1/pos/shifts/{shift_1_id}/z-report", headers=pos_setup["mgr_headers"])
    assert res.status_code == 200
    assert res.json()["shift_id"] == shift_1_id


def test_manager_cannot_view_different_store_z_report(pos_setup):
    # Manager at Store 1 attempts to view Cashier 2's shift at Store 2
    shifts_res = client.get("/api/v1/pos/shifts", headers=pos_setup["c2_headers"])
    shift_2_id = shifts_res.json()[0]["id"]

    res = client.get(f"/api/v1/pos/shifts/{shift_2_id}/z-report", headers=pos_setup["mgr_headers"])
    assert res.status_code == 403


def test_owner_can_view_all_tenant_z_reports(pos_setup):
    # Owner views Store 1 shift and Store 2 shift
    shifts_s1 = client.get("/api/v1/pos/shifts", headers=pos_setup["c1_headers"])
    shifts_s2 = client.get("/api/v1/pos/shifts", headers=pos_setup["c2_headers"])

    s1_id = shifts_s1.json()[0]["id"]
    s2_id = shifts_s2.json()[0]["id"]

    res1 = client.get(f"/api/v1/pos/shifts/{s1_id}/z-report", headers=pos_setup["owner_headers"])
    assert res1.status_code == 200
    assert res1.json()["shift_id"] == s1_id

    res2 = client.get(f"/api/v1/pos/shifts/{s2_id}/z-report", headers=pos_setup["owner_headers"])
    assert res2.status_code == 200
    assert res2.json()["shift_id"] == s2_id


def test_cross_tenant_shift_z_report_returns_404(pos_setup):
    # Tenant 2 user tries to access Tenant 1 shift
    shifts_s1 = client.get("/api/v1/pos/shifts", headers=pos_setup["c1_headers"])
    s1_id = shifts_s1.json()[0]["id"]

    res = client.get(f"/api/v1/pos/shifts/{s1_id}/z-report", headers=pos_setup["t2_headers"])
    assert res.status_code == 404


def test_accountant_forbidden_from_shift_management(pos_setup):
    # Accountant user does not have pos:shift_manage permission
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=pos_setup["acct_headers"],
        json={"opening_cash_float": 1000.00},
    )
    assert res.status_code == 403
