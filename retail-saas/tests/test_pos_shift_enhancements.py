import random
import uuid
from decimal import Decimal
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.order import Order
from app.models.payment import Payment
from app.models.pos_cash_movement import POSCashMovement
from app.models.pos_shift import POSShift
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.utils.constants import OrderStatus, PaymentStatus

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture(scope="module")
def enhancement_setup():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # Register tenant
        owner_email = f"pos_enh_owner_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"POS Enh Store {suffix}",
                "domain": f"enh-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Owner {suffix}",
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
        owner_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Create Store
        s1 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={"name": f"Store Alpha {suffix}", "code": f"EA{suffix[:4].upper()}"},
        )
        assert s1.status_code == 201
        store_id = s1.json()["id"]

        # Roles
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
                permissions=["pos:shift_manage", "billing:read", "billing:write"],
            )
            db.add(cashier_role)
            db.commit()

        manager_role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant_id, Role.name == "manager")
            .first()
        )
        if not manager_role:
            manager_role = Role(
                tenant_id=tenant_id,
                name="manager",
                is_system=False,
                permissions=["pos:shift_manage", "stores:read", "users:read"],
            )
            db.add(manager_role)
            db.commit()

        # Cashier 1
        c1_email = f"cashier1_{suffix}@retailtest.com"
        c1_pass = "CashierPass123!"
        c1_user = User(
            tenant_id=tenant_id,
            store_id=store_id,
            role_id=cashier_role.id,
            email=c1_email,
            password_hash=get_password_hash(c1_pass),
            full_name=f"Cashier One {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(c1_user)

        # Cashier 2
        c2_email = f"cashier2_{suffix}@retailtest.com"
        c2_pass = "CashierPass123!"
        c2_user = User(
            tenant_id=tenant_id,
            store_id=store_id,
            role_id=cashier_role.id,
            email=c2_email,
            password_hash=get_password_hash(c2_pass),
            full_name=f"Cashier Two {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(c2_user)

        # Manager
        mgr_email = f"mgr_{suffix}@retailtest.com"
        mgr_pass = "MgrPass123!"
        mgr_user = User(
            tenant_id=tenant_id,
            store_id=store_id,
            role_id=manager_role.id,
            email=mgr_email,
            password_hash=get_password_hash(mgr_pass),
            full_name=f"Manager One {suffix}",
            phone=_gen_phone(),
            is_active=True,
            is_deleted=False,
        )
        db.add(mgr_user)
        db.commit()

        # Logins
        l1 = client.post("/api/v1/auth/login", json={"email": c1_email, "password": c1_pass}).json()
        l2 = client.post("/api/v1/auth/login", json={"email": c2_email, "password": c2_pass}).json()
        lm = client.post("/api/v1/auth/login", json={"email": mgr_email, "password": mgr_pass}).json()

        return {
            "tenant_id": tenant_id,
            "store_id": store_id,
            "c1_headers": {"Authorization": f"Bearer {l1['access_token']}"},
            "c2_headers": {"Authorization": f"Bearer {l2['access_token']}"},
            "mgr_headers": {"Authorization": f"Bearer {lm['access_token']}"},
            "owner_headers": owner_headers,
            "c1_id": c1_user.id,
            "c2_id": c2_user.id,
            "mgr_id": mgr_user.id,
        }
    finally:
        db.close()


def test_open_shift_with_register_and_denominations(enhancement_setup):
    headers = enhancement_setup["c1_headers"]
    # 500*10 (5000) + 200*5 (1000) + 100*10 (1000) = 7000.00
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={
            "register_id": "POS-REG-01",
            "denominations": {"500": 10, "200": 5, "100": 10},
            "notes": "Morning shift opening with counted notes",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "open"
    assert data["register_id"] == "POS-REG-01"
    assert Decimal(str(data["opening_cash_float"])) == Decimal("7000.00")
    assert data["opening_denominations"]["500"] == 10


def test_open_shift_duplicate_register_rejected(enhancement_setup):
    headers = enhancement_setup["c2_headers"]
    # Cashier 2 tries to open a shift on the same register POS-REG-01
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={
            "register_id": "POS-REG-01",
            "opening_cash_float": 1000.00,
        },
    )
    assert res.status_code == 409
    assert "already has an active open shift" in res.text


def test_cash_movement_insufficient_drawer_cash_rejected(enhancement_setup):
    headers = enhancement_setup["c1_headers"]
    # Drawer only has opening float of 7000.00. Trying to drop 15000.00 should fail.
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={
            "movement_type": "CASH_DROP",
            "amount": 15000.00,
            "reason": "Mid-day safe deposit",
        },
    )
    assert res.status_code == 400
    assert "Insufficient drawer cash" in res.text


def test_cash_movement_with_sufficient_balance(enhancement_setup):
    headers = enhancement_setup["c1_headers"]
    # Drop 2000.00 from 7000.00
    res = client.post(
        "/api/v1/pos/shifts/cash-movement",
        headers=headers,
        json={
            "movement_type": "CASH_DROP",
            "amount": 2000.00,
            "reason": "Safe deposit of 2000",
            "authorized_by": enhancement_setup["mgr_id"],
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert Decimal(str(data["amount"])) == Decimal("2000.00")
    assert data["movement_type"] == "CASH_DROP"


def test_x_report_mid_shift_reading(enhancement_setup):
    headers = enhancement_setup["c1_headers"]
    curr = client.get("/api/v1/pos/shifts/current", headers=headers).json()
    shift_id = curr["id"]

    res = client.get(f"/api/v1/pos/shifts/{shift_id}/x-report", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["shift_id"] == shift_id
    assert data["status"] == "open"
    assert data["register_id"] == "POS-REG-01"
    # Current cash = 7000 opening - 2000 drop = 5000.00
    assert Decimal(str(data["current_drawer_cash"])) == Decimal("5000.00")
    assert len(data["movements"]) == 1


def test_export_z_report_thermal_slip(enhancement_setup):
    headers = enhancement_setup["c1_headers"]
    curr = client.get("/api/v1/pos/shifts/current", headers=headers).json()
    shift_id = curr["id"]

    # 1. Default mode is 'preview' (image/png for Swagger UI direct visual rendering)
    prev_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal", headers=headers)
    assert prev_res.status_code == 200
    assert "image/png" in prev_res.headers["content-type"]
    assert len(prev_res.content) > 100

    # Explicit preview mode
    prev_exp = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=preview", headers=headers)
    assert prev_exp.status_code == 200
    assert "image/png" in prev_exp.headers["content-type"]

    # 2. Text mode (raw ESC/POS text stream)
    text_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=text", headers=headers)
    assert text_res.status_code == 200
    assert "text/plain" in text_res.headers["content-type"]
    text = text_res.text
    assert "POS SHIFT Z-REPORT" in text
    assert "CASH DRAWER RECONCILIATION" in text
    assert "POS-REG-01" in text
    assert "EXPECTED CASH" in text

    # 3. Download mode (text file attachment)
    dl_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=download", headers=headers)
    assert dl_res.status_code == 200
    assert "text/plain" in dl_res.headers["content-type"]
    assert "attachment" in dl_res.headers["content-disposition"]
    assert "POS SHIFT Z-REPORT" in dl_res.text

    # 4. PDF mode (80mm thermal receipt PDF attachment)
    pdf_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers["content-type"]
    assert "attachment" in pdf_res.headers["content-disposition"]
    assert len(pdf_res.content) > 100

    # 5. View mode (styled HTML with auto-print script)
    view_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=view", headers=headers)
    assert view_res.status_code == 200
    assert "text/html" in view_res.headers["content-type"]
    assert "window.print()" in view_res.text

    # 6. HTML mode (styled raw HTML)
    html_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=html", headers=headers)
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    assert "POS SHIFT Z-REPORT" in html_res.text

    # 7. JSON mode (structured payload)
    json_res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/thermal?mode=json", headers=headers)
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    data = json_res.json()
    assert data["success"] is True
    assert data["shift_id"] == shift_id
    assert "text_payload" in data
    assert "html" in data


def test_export_z_report_multi_format_endpoint(enhancement_setup):
    headers = enhancement_setup["c1_headers"]
    curr = client.get("/api/v1/pos/shifts/current", headers=headers).json()
    shift_id = curr["id"]

    res = client.get(f"/api/v1/pos/shifts/{shift_id}/z-report/pdf?format=csv", headers=headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "POS SHIFT Z-REPORT" in res.text


def test_manager_force_close_shift(enhancement_setup):
    mgr_headers = enhancement_setup["mgr_headers"]
    c1_headers = enhancement_setup["c1_headers"]

    curr = client.get("/api/v1/pos/shifts/current", headers=c1_headers).json()
    shift_id = curr["id"]

    # Cashier 2 should not be allowed to force close
    fail_res = client.post(
        f"/api/v1/pos/shifts/{shift_id}/force-close",
        headers=enhancement_setup["c2_headers"],
        json={"closing_cash_counted": 5000.00, "reason": "Cashier left"},
    )
    assert fail_res.status_code == 403

    # Manager force closes with exact expected cash = 5000.00
    res = client.post(
        f"/api/v1/pos/shifts/{shift_id}/force-close",
        headers=mgr_headers,
        json={
            "closing_cash_counted": 5000.00,
            "reason": "Cashier forgot to close and went home",
            "notes": "Verified drawer count by Manager",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["shift"]["status"] == "closed"
    assert data["variance_status"] == "exact"
    assert data["closed_by"] == enhancement_setup["mgr_id"]
    assert "FORCE CLOSED by Manager" in data["shift"]["notes"]


def test_list_shifts_enhanced_filters(enhancement_setup):
    headers = enhancement_setup["mgr_headers"]
    res = client.get(
        "/api/v1/pos/shifts",
        headers=headers,
        params={"register_id": "POS-REG-01", "status": "closed"},
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert items[0]["register_id"] == "POS-REG-01"
    assert items[0]["status"] == "closed"


def test_admin_owner_can_open_shift_auto_store(enhancement_setup):
    headers = enhancement_setup["owner_headers"]
    # Admin/Owner has store_id=None, but open shift auto-resolves to the tenant's active store
    res = client.post(
        "/api/v1/pos/shifts/open",
        headers=headers,
        json={
            "register_id": "ADMIN-REG-01",
            "opening_cash_float": 5000.00,
            "denominations": {"500": 8, "200": 5},
            "notes": "Admin testing POS shift",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["status"] == "open"
    assert data["store_id"] == enhancement_setup["store_id"]
    assert data["register_id"] == "ADMIN-REG-01"

    # Admin can also get current shift
    curr_res = client.get("/api/v1/pos/shifts/current", headers=headers)
    assert curr_res.status_code == 200
    assert curr_res.json()["id"] == data["id"]

    # Admin can close the shift
    close_res = client.post(
        "/api/v1/pos/shifts/close",
        headers=headers,
        json={"closing_cash_counted": 5000.00, "notes": "Admin test shift closed"},
    )
    assert close_res.status_code == 200
    assert close_res.json()["shift"]["status"] == "closed"

