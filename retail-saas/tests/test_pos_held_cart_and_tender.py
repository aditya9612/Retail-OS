import random
import uuid
from decimal import Decimal
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.payment import Payment
from app.models.pos_held_cart import POSHeldCart
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.utils.constants import UserRole

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture(scope="module")
def setup_fixture():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # 1. Register Tenant 1
        owner_email = f"held_owner_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"POS Superstore {suffix}",
                "domain": f"held-{suffix}",
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
            json={
                "name": f"Store Alpha {suffix}",
                "code": f"SA_{suffix}",
                "city": "Pune",
                "state": "Maharashtra",
            },
        )
        assert s1.status_code == 201, s1.text
        store1_id = s1.json()["id"]

        s2 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={
                "name": f"Store Beta {suffix}",
                "code": f"SB_{suffix}",
                "city": "Mumbai",
                "state": "Maharashtra",
            },
        )
        assert s2.status_code == 201, s2.text
        store2_id = s2.json()["id"]

        # 3. Create Cashier 1 at Store 1
        cashier_role = (
            db.query(Role)
            .filter(Role.name == UserRole.CASHIER.value, Role.tenant_id == tenant1_id)
            .first()
        )
        c1_email = f"cashier1_{suffix}@retailtest.com"
        c1_res = client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": c1_email,
                "full_name": "Cashier One",
                "phone": _gen_phone(),
                "password": "Password123!",
                "role_id": cashier_role.id,
                "store_id": store1_id,
            },
        )
        assert c1_res.status_code == 201, c1_res.text
        c1_id = c1_res.json()["id"]

        c1_log = client.post(
            "/api/v1/auth/login",
            json={"email": c1_email, "password": "Password123!"},
        )
        assert c1_log.status_code == 200
        c1_headers = {"Authorization": f"Bearer {c1_log.json()['access_token']}"}

        # 4. Create Cashier 2 at Store 2
        c2_email = f"cashier2_{suffix}@retailtest.com"
        c2_res = client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": c2_email,
                "full_name": "Cashier Two",
                "phone": _gen_phone(),
                "password": "Password123!",
                "role_id": cashier_role.id,
                "store_id": store2_id,
            },
        )
        assert c2_res.status_code == 201, c2_res.text
        c2_id = c2_res.json()["id"]

        c2_log = client.post(
            "/api/v1/auth/login",
            json={"email": c2_email, "password": "Password123!"},
        )
        assert c2_log.status_code == 200
        c2_headers = {"Authorization": f"Bearer {c2_log.json()['access_token']}"}

        # 5. Create Products with Inventory
        p1 = Product(
            tenant_id=tenant1_id,
            name=f"Held Test Item A {suffix}",
            sku=f"SKU-HA-{suffix}",
            barcode=f"BAR-HA-{suffix}",
            selling_price=Decimal("200.00"),
            cost_price=Decimal("120.00"),
            tax_rate=Decimal("18.00"),
            is_active=True,
        )
        p2 = Product(
            tenant_id=tenant1_id,
            name=f"Held Test Item B {suffix}",
            sku=f"SKU-HB-{suffix}",
            barcode=f"BAR-HB-{suffix}",
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            tax_rate=Decimal("12.00"),
            is_active=True,
        )
        db.add_all([p1, p2])
        db.commit()
        db.refresh(p1)
        db.refresh(p2)

        inv1 = Inventory(
            tenant_id=tenant1_id,
            store_id=store1_id,
            product_id=p1.id,
            quantity=100,
        )
        inv2 = Inventory(
            tenant_id=tenant1_id,
            store_id=store1_id,
            product_id=p2.id,
            quantity=100,
        )
        db.add_all([inv1, inv2])
        db.commit()

        # 6. Create Customer
        cust = Customer(
            tenant_id=tenant1_id,
            name=f"Held Customer {suffix}",
            phone=_gen_phone(),
            email=f"cust_{suffix}@test.com",
        )
        db.add(cust)
        db.commit()
        db.refresh(cust)

        # 7. Register Tenant 2 for isolation tests
        t2_owner_email = f"t2_owner_{suffix}@retailtest.com"
        reg_t2 = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Tenant 2 Store {suffix}",
                "domain": f"t2-{suffix}",
                "owner_email": t2_owner_email,
                "owner_name": f"T2 Owner {suffix}",
                "password": "Password123!",
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_t2.status_code == 200
        t2_log = client.post(
            "/api/v1/auth/login",
            json={"email": t2_owner_email, "password": "Password123!"},
        )
        t2_headers = {"Authorization": f"Bearer {t2_log.json()['access_token']}"}

        return {
            "tenant1_id": tenant1_id,
            "store1_id": store1_id,
            "store2_id": store2_id,
            "c1_headers": c1_headers,
            "c1_id": c1_id,
            "c2_headers": c2_headers,
            "c2_id": c2_id,
            "owner_headers": owner_headers,
            "t2_headers": t2_headers,
            "p1_id": p1.id,
            "p2_id": p2.id,
            "customer_id": cust.id,
        }
    finally:
        db.close()


# ============================================================================
# PHASE 4.2: POS HOLD / PARK CART TESTS
# ============================================================================

def test_hold_empty_cart_rejected(setup_fixture):
    headers = setup_fixture["c1_headers"]
    # Ensure active cart is empty
    client.delete(f"/api/v1/billing/cart/remove-item?product_id={setup_fixture['p1_id']}", headers=headers)
    
    res = client.post(
        "/api/v1/billing/cart/hold",
        headers=headers,
        json={"notes": "Holding empty cart"},
    )
    assert res.status_code == 400
    assert "cart is empty" in res.text.lower()


def test_hold_active_cart_success(setup_fixture):
    headers = setup_fixture["c1_headers"]
    p1_id = setup_fixture["p1_id"]
    p2_id = setup_fixture["p2_id"]
    store_id = setup_fixture["store1_id"]

    # 1. Add items to active cart
    res_add1 = client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": p1_id, "quantity": 2, "store_id": store_id},
    )
    assert res_add1.status_code == 200

    res_add2 = client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": p2_id, "quantity": 1, "store_id": store_id},
    )
    assert res_add2.status_code == 200

    # 2. Hold active cart
    res_hold = client.post(
        "/api/v1/billing/cart/hold",
        headers=headers,
        json={
            "notes": "Customer went to get ATM cash",
            "customer_name": "Ramesh Patil",
            "customer_phone": "9876543210",
        },
    )
    assert res_hold.status_code == 200, res_hold.text
    data = res_hold.json()

    assert data["status"] == "held"
    assert data["items_count"] == 2
    assert "HOLD-" in data["hold_reference"]
    assert data["customer_name"] == "Ramesh Patil"
    assert data["customer_phone"] == "9876543210"
    assert Decimal(str(data["grand_total"])) > Decimal("0.00")

    # 3. Verify active cart was cleared
    res_cart = client.get("/api/v1/billing/cart", headers=headers)
    assert res_cart.status_code == 200
    assert len(res_cart.json()["items"]) == 0


def test_inventory_not_deducted_when_cart_is_held(setup_fixture):
    db = SessionLocal()
    try:
        p1_id = setup_fixture["p1_id"]
        store1_id = setup_fixture["store1_id"]
        inv = (
            db.query(Inventory)
            .filter(Inventory.store_id == store1_id, Inventory.product_id == p1_id)
            .first()
        )
        assert inv is not None
        # Inventory quantity should remain 100 because cart was merely parked
        assert inv.quantity == 100
    finally:
        db.close()


def test_list_held_carts(setup_fixture):
    headers = setup_fixture["c1_headers"]
    res = client.get("/api/v1/billing/cart/held", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["status"] == "held"


def test_search_held_carts(setup_fixture):
    headers = setup_fixture["c1_headers"]
    # Search by customer name
    res = client.get("/api/v1/billing/cart/held?search=Ramesh", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert "Ramesh" in data["items"][0]["customer_name"]

    # Search non-existing
    res_none = client.get("/api/v1/billing/cart/held?search=NonExistentReferenceXYZ", headers=headers)
    assert res_none.status_code == 200
    assert res_none.json()["total"] == 0


def test_get_held_cart_by_id(setup_fixture):
    headers = setup_fixture["c1_headers"]
    list_res = client.get("/api/v1/billing/cart/held", headers=headers)
    hold_id = list_res.json()["items"][0]["id"]

    res = client.get(f"/api/v1/billing/cart/held/{hold_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == hold_id


def test_cross_store_cashier_cannot_access_held_cart(setup_fixture):
    # Cashier 2 at Store 2 tries to access Store 1's held cart
    list_res = client.get("/api/v1/billing/cart/held", headers=setup_fixture["c1_headers"])
    hold_id = list_res.json()["items"][0]["id"]

    res = client.get(f"/api/v1/billing/cart/held/{hold_id}", headers=setup_fixture["c2_headers"])
    assert res.status_code == 403


def test_cross_tenant_held_cart_returns_404(setup_fixture):
    list_res = client.get("/api/v1/billing/cart/held", headers=setup_fixture["c1_headers"])
    hold_id = list_res.json()["items"][0]["id"]

    res = client.get(f"/api/v1/billing/cart/held/{hold_id}", headers=setup_fixture["t2_headers"])
    assert res.status_code == 404


def test_recall_held_cart_blocked_when_active_cart_has_items(setup_fixture):
    headers = setup_fixture["c1_headers"]
    list_res = client.get("/api/v1/billing/cart/held", headers=headers)
    hold_id = list_res.json()["items"][0]["id"]

    # Add an item to active cart first
    client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": setup_fixture["p1_id"], "quantity": 1, "store_id": setup_fixture["store1_id"]},
    )

    # Attempt recall without force_override
    res = client.post(
        f"/api/v1/billing/cart/held/{hold_id}/recall",
        headers=headers,
        json={"force_override": False},
    )
    assert res.status_code in (409, 400)
    assert "active cart" in res.text.lower()


def test_recall_held_cart_success(setup_fixture):
    headers = setup_fixture["c1_headers"]
    list_res = client.get("/api/v1/billing/cart/held", headers=headers)
    hold_id = list_res.json()["items"][0]["id"]

    # Recall with force_override=True to restore items
    res_recall = client.post(
        f"/api/v1/billing/cart/held/{hold_id}/recall",
        headers=headers,
        json={"force_override": True},
    )
    assert res_recall.status_code == 200, res_recall.text
    cart_data = res_recall.json()
    assert len(cart_data["items"]) == 2  # Item A and Item B

    # Verify held cart record is now marked as recalled
    res_get = client.get(f"/api/v1/billing/cart/held/{hold_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["status"] == "recalled"
    assert res_get.json()["recalled_at"] is not None


def test_recall_already_recalled_cart_rejected(setup_fixture):
    headers = setup_fixture["c1_headers"]
    list_res = client.get("/api/v1/billing/cart/held?status=recalled", headers=headers)
    recalled_id = list_res.json()["items"][0]["id"]

    res = client.post(
        f"/api/v1/billing/cart/held/{recalled_id}/recall",
        headers=headers,
        json={"force_override": True},
    )
    assert res.status_code in (409, 400)
    assert "already recalled" in res.text.lower()


def test_cancel_held_cart_success(setup_fixture):
    headers = setup_fixture["c1_headers"]
    store_id = setup_fixture["store1_id"]

    # Create a fresh cart and hold it
    client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": setup_fixture["p1_id"], "quantity": 1, "store_id": store_id},
    )
    hold_res = client.post(
        "/api/v1/billing/cart/hold",
        headers=headers,
        json={"notes": "Cart to be cancelled"},
    )
    assert hold_res.status_code == 200
    hold_id = hold_res.json()["id"]

    # Cancel the held cart
    res_cancel = client.delete(
        f"/api/v1/billing/cart/held/{hold_id}?reason=Customer%20left%20store",
        headers=headers,
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "cancelled"
    assert res_cancel.json()["cancelled_at"] is not None
    assert "Customer left store" in res_cancel.json()["notes"]


def test_cancel_already_cancelled_cart_rejected(setup_fixture):
    headers = setup_fixture["c1_headers"]
    list_res = client.get("/api/v1/billing/cart/held?status=cancelled", headers=headers)
    cancelled_id = list_res.json()["items"][0]["id"]

    res = client.delete(
        f"/api/v1/billing/cart/held/{cancelled_id}",
        headers=headers,
    )
    assert res.status_code in (409, 400)
    assert "already cancelled" in res.text.lower()


# ============================================================================
# PHASE 4.3: TENDER CASH & CHANGE CALCULATION TESTS
# ============================================================================

def test_calculate_tender_change_exact(setup_fixture):
    headers = setup_fixture["c1_headers"]
    res = client.post(
        "/api/v1/billing/tender-change/calculate",
        headers=headers,
        json={"payable_amount": 500.00, "tendered_amount": 500.00},
    )
    assert res.status_code == 200
    data = res.json()
    assert Decimal(str(data["change_due"])) == Decimal("0.00")
    assert data["is_exact"] is True


def test_calculate_tender_change_overpayment(setup_fixture):
    headers = setup_fixture["c1_headers"]
    res = client.post(
        "/api/v1/billing/tender-change/calculate",
        headers=headers,
        json={"payable_amount": 420.50, "tendered_amount": 500.00},
    )
    assert res.status_code == 200
    data = res.json()
    assert Decimal(str(data["change_due"])) == Decimal("79.50")
    assert data["is_exact"] is False


def test_calculate_tender_change_underpayment_rejected(setup_fixture):
    headers = setup_fixture["c1_headers"]
    res = client.post(
        "/api/v1/billing/tender-change/calculate",
        headers=headers,
        json={"payable_amount": 500.00, "tendered_amount": 400.00},
    )
    assert res.status_code == 400
    assert "insufficient cash tendered" in res.text.lower()


def test_calculate_tender_change_decimal_precision(setup_fixture):
    headers = setup_fixture["c1_headers"]
    res = client.post(
        "/api/v1/billing/tender-change/calculate",
        headers=headers,
        json={"payable_amount": 123.45, "tendered_amount": 150.00},
    )
    assert res.status_code == 200
    data = res.json()
    assert Decimal(str(data["change_due"])) == Decimal("26.55")


def test_checkout_with_cash_tendered_and_change_recorded(setup_fixture):
    headers = setup_fixture["c1_headers"]
    p1_id = setup_fixture["p1_id"]
    store_id = setup_fixture["store1_id"]

    # 1. Add item to cart
    client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": p1_id, "quantity": 1, "store_id": store_id},
    )

    cart = client.get("/api/v1/billing/cart", headers=headers).json()
    grand_total = Decimal(str(cart["grand_total"]))

    # Tender 500 for the bill
    tendered = grand_total + Decimal("100.00")
    change = Decimal("100.00")

    # 2. Checkout invoice
    res_inv = client.post(
        "/api/v1/invoices",
        headers=headers,
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [
                {
                    "payment_mode": "cash",
                    "amount": float(grand_total),
                    "amount_tendered": float(tendered),
                    "change_due": float(change),
                    "transaction_reference": "POS-CASH-001",
                }
            ],
        },
    )
    assert res_inv.status_code in (200, 201), res_inv.text
    inv_data = res_inv.json()
    assert inv_data["id"] is not None

    # Verify payment record has amount_tendered and change_due
    db = SessionLocal()
    try:
        payment = (
            db.query(Payment)
            .filter(Payment.order_id == inv_data["order_id"], Payment.payment_method == "cash")
            .first()
        )
        assert payment is not None
        assert Decimal(str(payment.amount)) == grand_total
        assert Decimal(str(payment.amount_tendered)) == tendered
        assert Decimal(str(payment.change_due)) == change
    finally:
        db.close()


def test_checkout_with_insufficient_cash_tendered_rejected(setup_fixture):
    headers = setup_fixture["c1_headers"]
    p1_id = setup_fixture["p1_id"]
    store_id = setup_fixture["store1_id"]

    # Add item to cart
    client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": p1_id, "quantity": 1, "store_id": store_id},
    )

    cart = client.get("/api/v1/billing/cart", headers=headers).json()
    grand_total = Decimal(str(cart["grand_total"]))

    # Tender less than amount
    res_inv = client.post(
        "/api/v1/invoices",
        headers=headers,
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [
                {
                    "payment_mode": "cash",
                    "amount": float(grand_total),
                    "amount_tendered": float(grand_total - Decimal("50.00")),
                    "change_due": 0.00,
                }
            ],
        },
    )
    assert res_inv.status_code == 400
    assert "cannot be less than payable" in res_inv.text.lower()


def test_checkout_with_split_payment_cash_and_upi(setup_fixture):
    headers = setup_fixture["c1_headers"]
    p1_id = setup_fixture["p1_id"]
    store_id = setup_fixture["store1_id"]

    # Add item to cart
    client.post(
        "/api/v1/billing/cart/add-item",
        headers=headers,
        json={"product_id": p1_id, "quantity": 1, "store_id": store_id},
    )

    cart = client.get("/api/v1/billing/cart", headers=headers).json()
    grand_total = Decimal(str(cart["grand_total"]))

    cash_part = (grand_total / Decimal("2")).quantize(Decimal("0.01"))
    upi_part = grand_total - cash_part

    cash_tendered = cash_part + Decimal("50.00")
    change = Decimal("50.00")

    res_inv = client.post(
        "/api/v1/invoices",
        headers=headers,
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [
                {
                    "payment_mode": "cash",
                    "amount": float(cash_part),
                    "amount_tendered": float(cash_tendered),
                    "change_due": float(change),
                    "transaction_reference": "SPLIT-CASH-002",
                },
                {
                    "payment_mode": "upi",
                    "amount": float(upi_part),
                    "transaction_reference": "UPI-REF-002",
                },
            ],
        },
    )
    assert res_inv.status_code in (200, 201), res_inv.text
    inv_data = res_inv.json()
    assert inv_data["id"] is not None

    # Check both payment rows exist in DB
    db = SessionLocal()
    try:
        payments = db.query(Payment).filter(Payment.order_id == inv_data["order_id"]).all()
        assert len(payments) == 2
        cash_row = next(p for p in payments if p.payment_method == "cash")
        assert Decimal(str(cash_row.amount_tendered)) == cash_tendered
        assert Decimal(str(cash_row.change_due)) == change

        upi_row = next(p for p in payments if p.payment_method == "upi")
        assert Decimal(str(upi_row.amount)) == upi_part
    finally:
        db.close()
