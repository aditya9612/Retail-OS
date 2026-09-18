import io
import pytest
from openpyxl import Workbook
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.order import Order, OrderTracking

client = TestClient(app)


@pytest.fixture
def auth_setup_factory():
    def _create(prefix: str):
        email = f"{prefix}-owner@example.com"
        reg = client.post(
            "/api/v1/auth/register",
            params={
                "tenant_name": f"{prefix.capitalize()} Store",
                "slug": prefix,
                "email": email,
                "admin_name": f"{prefix.capitalize()} Admin",
                "password": "Password123!",
            },
        )
        assert reg.status_code == 200, reg.text

        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        assert login.status_code == 200, login.text
        data = login.json()
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        user_me = client.get("/api/v1/users/me", headers=headers).json()
        return headers, user_me

    return _create


@pytest.fixture
def tenant_a(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"t-a-{unique_slug}")
    return headers, user


@pytest.fixture
def tenant_b(auth_setup_factory, unique_slug):
    headers, user = auth_setup_factory(f"t-b-{unique_slug}")
    return headers, user


import uuid
from app.models.store import Store


def create_delivery_for_tenant(tenant_headers, user_data, initial_status="pending"):
    """Helper to create a valid delivery in the database for the given tenant."""
    db = SessionLocal()
    try:
        tenant_id = user_data["tenant_id"]
        uid = uuid.uuid4().hex[:8]
        store = Store(
            tenant_id=tenant_id,
            name=f"Test Store {uid}",
            code=f"TS-{uid}",
        )
        db.add(store)
        db.flush()

        order = Order(
            tenant_id=tenant_id,
            store_id=store.id,
            order_number=f"ORD-DEL-{uid}",
            order_type="pos",
            status="confirmed",
        )
        db.add(order)
        db.flush()

        delivery = Delivery(
            tenant_id=tenant_id,
            order_id=order.id,
            status=initial_status,
            delivery_person=None,
            tracking_number=None,
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery.id, order.id
    finally:
        db.close()


def create_order_for_tenant(tenant_headers, user_data, order_status="confirmed", customer_id=None, delivery_address=None):
    """Helper to create an order without delivery for the given tenant."""
    db = SessionLocal()
    try:
        tenant_id = user_data["tenant_id"]
        uid = uuid.uuid4().hex[:8]
        store = Store(
            tenant_id=tenant_id,
            name=f"Test Store {uid}",
            code=f"TS-{uid}",
        )
        db.add(store)
        db.flush()

        order = Order(
            tenant_id=tenant_id,
            store_id=store.id,
            customer_id=customer_id,
            order_number=f"ORD-DEL-{uid}",
            order_type="pos",
            status=order_status,
            delivery_address=delivery_address,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order.id
    finally:
        db.close()


def create_customer_for_tenant(user_data, name="John Doe", phone=None):
    """Helper to create a customer for the given tenant."""
    db = SessionLocal()
    try:
        tenant_id = user_data["tenant_id"]
        uid = uuid.uuid4().hex[:8]
        if phone is None:
            phone = f"+12345{uid[:5]}"
        customer = Customer(
            tenant_id=tenant_id,
            name=name,
            phone=phone,
            email=f"cust-{uid}@example.com",
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer.id
    finally:
        db.close()




# ============================================================================
# 1. GET /api/v1/delivery
# ============================================================================

def test_list_deliveries_empty(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "No deliveries found"
    assert body["data"] == []
    assert body["total"] == 0


def test_list_deliveries_with_data(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.get("/api/v1/delivery", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Deliveries retrieved successfully"
    assert body["total"] >= 1
    assert isinstance(body["data"], list)

    item = next((d for d in body["data"] if d["id"] == del_id), None)
    assert item is not None
    assert item["id"] == del_id
    assert item["tenant_id"] == user["tenant_id"]
    assert item["order_id"] == order_id
    assert item["status"] == "pending"
    assert "created_at" in item
    assert "additionalProp1" not in item


def test_list_deliveries_tenant_isolation(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, user_b = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    # Tenant B lists deliveries: must NOT see Tenant A's delivery
    resp_b = client.get("/api/v1/delivery", headers=headers_b)
    assert resp_b.status_code == 200
    body_b = resp_b.json()
    assert not any(d["id"] == del_id_a for d in body_b["data"])


# ============================================================================
# 2. GET /api/v1/delivery/{delivery_id}
# ============================================================================

def test_get_delivery_success(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user)

    resp = client.get(f"/api/v1/delivery/{del_id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery retrieved successfully"
    data = body["data"]
    assert data["id"] == del_id
    assert data["tenant_id"] == user["tenant_id"]
    assert data["order_id"] == order_id
    assert data["status"] == "pending"


def test_get_delivery_zero_id(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/0", headers=headers)
    assert resp.status_code == 422


def test_get_delivery_negative_id(tenant_a):
    headers, _ = tenant_a
    resp_neg1 = client.get("/api/v1/delivery/-1", headers=headers)
    assert resp_neg1.status_code == 422

    resp_neg100 = client.get("/api/v1/delivery/-100", headers=headers)
    assert resp_neg100.status_code == 422


def test_get_delivery_decimal_id(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/1.5", headers=headers)
    assert resp.status_code == 422


def test_get_delivery_alphabetic_id(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/abc", headers=headers)
    assert resp.status_code == 422


def test_get_delivery_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/999999", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_get_delivery_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    # Tenant B tries to access Tenant A's delivery
    resp = client.get(f"/api/v1/delivery/{del_id_a}", headers=headers_b)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


# ============================================================================
# 3. PATCH /api/v1/delivery/{delivery_id}/status
# ============================================================================

def test_update_status_success(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery status updated successfully"
    assert body["data"]["status"] == "assigned"


def test_update_status_delivered_timestamp_and_tracking(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user, initial_status="out_for_delivery")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "delivered"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "delivered"
    assert body["data"]["delivered_at"] is not None

    # Verify OrderTracking record was persisted in DB
    db = SessionLocal()
    try:
        tracking = (
            db.query(OrderTracking)
            .filter(OrderTracking.order_id == order_id, OrderTracking.status == "delivered")
            .first()
        )
        assert tracking is not None
        assert "delivered" in tracking.remarks.lower()
    finally:
        db.close()


def test_update_status_casing_and_whitespace_normalized(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "  ASSIGNED  "},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "assigned"


def test_update_status_zero_id(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/0/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_negative_id(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/-1/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_decimal_id(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/1.5/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_non_integer_id(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/xyz/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_missing_status(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_null_status(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": None},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_empty_status(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": ""},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_whitespace_status(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "    "},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_random_string(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "random_status"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_numeric_string(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "12345"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_special_chars(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user)

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "@@@"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_status_same_status(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "pending"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "already" in body["message"].lower()


def test_update_status_invalid_transition_delivered(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="delivered")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "pending"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot change delivery status" in body["message"].lower()


def test_update_status_invalid_transition_cancelled(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="cancelled")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot change delivery status" in body["message"].lower()


def test_update_status_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/999999/status",
        json={"status": "assigned"},
        headers=headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_update_status_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    # Tenant B tries to update Tenant A's delivery
    resp = client.patch(
        f"/api/v1/delivery/{del_id_a}/status",
        json={"status": "assigned"},
        headers=headers_b,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


# ============================================================================
# 4. POST /api/v1/delivery (Create Shipment)
# ============================================================================

def test_create_delivery_success_minimal(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user, order_status="confirmed")

    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery created successfully"
    assert body["data"]["order_id"] == order_id
    assert body["data"]["status"] == "pending"
    assert body["data"]["delivery_person"] is None
    assert body["data"]["tracking_number"] is None

    # Verify OrderTracking in DB
    db = SessionLocal()
    try:
        tracking = db.query(OrderTracking).filter(OrderTracking.order_id == order_id).first()
        assert tracking is not None
        assert tracking.status == "pending"
    finally:
        db.close()


def test_create_delivery_success_with_partner_and_tracking(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user, order_status="confirmed")

    resp = client.post(
        "/api/v1/delivery",
        json={
            "order_id": order_id,
            "delivery_person": "Alex Smith",
            "tracking_number": "TRK-987654",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "assigned"
    assert body["data"]["delivery_person"] == "Alex Smith"
    assert body["data"]["tracking_number"] == "TRK-987654"


def test_create_delivery_duplicate_order(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)

    # First creation succeeds
    resp1 = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp1.status_code == 201

    # Second creation fails with 409 Conflict
    resp2 = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp2.status_code == 409
    body2 = resp2.json()
    assert body2["success"] is False
    assert "already exists" in body2["message"].lower()


@pytest.mark.parametrize("bad_status", ["cancelled", "returned", "refunded"])
def test_create_delivery_order_terminal_status(tenant_a, bad_status):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user, order_status=bad_status)

    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert f"cannot create delivery for order in '{bad_status}' status" in body["message"].lower()


def test_create_delivery_order_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": 999999},
        headers=headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Order not found"


def test_create_delivery_cross_tenant_order(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    order_id_a = create_order_for_tenant(headers_a, user_a)

    # Tenant B tries to create delivery for Tenant A's order
    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id_a},
        headers=headers_b,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Order not found"


@pytest.mark.parametrize("invalid_order_id", [0, -1, -99, 12.34, "abc", None])
def test_create_delivery_invalid_order_id(tenant_a, invalid_order_id):
    headers, _ = tenant_a
    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": invalid_order_id},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "invalid_name",
    ["John Doe 123", "", "   ", "J", "Alex@Smith", "12345"],
)
def test_create_delivery_invalid_delivery_person(tenant_a, invalid_name):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)

    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id, "delivery_person": invalid_name},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "invalid_tracking",
    ["", "   ", "TR", "TRK$$$123", "   AB   "],
)
def test_create_delivery_invalid_tracking_number(tenant_a, invalid_tracking):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)

    resp = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id, "tracking_number": invalid_tracking},
        headers=headers,
    )
    assert resp.status_code == 422


# ============================================================================
# 5. PATCH /api/v1/delivery/{delivery_id}/cancel (Cancel Delivery)
# ============================================================================

def test_cancel_delivery_missing_reason_rejected_with_422(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/cancel",
        json={},
        headers=headers,
    )
    assert resp.status_code == 422
def test_cancel_delivery_success_with_reason(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user, initial_status="assigned")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/cancel",
        json={"reason": "Customer cancelled order"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "cancelled"

    db = SessionLocal()
    try:
        tracking = (
            db.query(OrderTracking)
            .filter(OrderTracking.order_id == order_id)
            .order_by(OrderTracking.created_at.desc())
            .first()
        )
        assert tracking is not None
        assert tracking.status == "cancelled"
        assert "Customer cancelled order" in tracking.remarks
    finally:
        db.close()


def test_cancel_delivery_already_cancelled(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="cancelled")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/cancel",
        json={"reason": "Repeat cancellation"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "already cancelled" in body["message"].lower()


def test_cancel_delivery_already_delivered(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="delivered")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/cancel",
        json={"reason": "Try to cancel"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot cancel a delivered shipment" in body["message"].lower()


@pytest.mark.parametrize("invalid_reason", ["", "   "])
def test_cancel_delivery_invalid_reason(tenant_a, invalid_reason):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/cancel",
        json={"reason": invalid_reason},
        headers=headers,
    )
    assert resp.status_code == 422


def test_cancel_delivery_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/999999/cancel",
        json={"reason": "Does not exist"},
        headers=headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_cancel_delivery_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    resp = client.patch(
        f"/api/v1/delivery/{del_id_a}/cancel",
        json={"reason": "Hacking"},
        headers=headers_b,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_cancel_delivery_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.patch(
        f"/api/v1/delivery/{invalid_id}/cancel",
        json={},
        headers=headers,
    )
    assert resp.status_code == 422


# ============================================================================
# 6. PATCH /api/v1/delivery/{delivery_id}/partner (Assign Delivery Partner)
# ============================================================================

def test_assign_partner_success(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={
            "delivery_person": "Robert Downey",
            "tracking_number": "TRK-RDJ-001",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery partner assigned successfully"
    assert body["data"]["status"] == "assigned"
    assert body["data"]["delivery_person"] == "Robert Downey"
    assert body["data"]["tracking_number"] == "TRK-RDJ-001"

    db = SessionLocal()
    try:
        tracking = (
            db.query(OrderTracking)
            .filter(OrderTracking.order_id == order_id)
            .order_by(OrderTracking.created_at.desc())
            .first()
        )
        assert tracking is not None
        assert tracking.status == "assigned"
        assert "Robert Downey" in tracking.remarks
    finally:
        db.close()


def test_assign_partner_delivered_fails(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="delivered")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={"delivery_person": "Robert Downey"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot assign delivery partner" in body["message"].lower()


def test_assign_partner_cancelled_fails(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="cancelled")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={"delivery_person": "Robert Downey"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot assign delivery partner" in body["message"].lower()


@pytest.mark.parametrize(
    "invalid_name",
    ["", "   ", "Robert 123", "R", "Robert@Downey", None],
)
def test_assign_partner_invalid_name(tenant_a, invalid_name):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={"delivery_person": invalid_name},
        headers=headers,
    )
    assert resp.status_code == 422


def test_assign_partner_invalid_tracking(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={"delivery_person": "Valid Name", "tracking_number": ""},
        headers=headers,
    )
    assert resp.status_code == 422


def test_assign_partner_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/999999/partner",
        json={"delivery_person": "Valid Name"},
        headers=headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_assign_partner_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    resp = client.patch(
        f"/api/v1/delivery/{del_id_a}/partner",
        json={"delivery_person": "Valid Name"},
        headers=headers_b,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


# ============================================================================
# 7. PATCH /api/v1/delivery/{delivery_id}/address (Update Delivery Address)
# ============================================================================

def test_update_address_success(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user, initial_status="pending")

    new_address = "456 Commerce Boulevard, Suite 100, New York, NY 10001"
    resp = client.patch(
        f"/api/v1/delivery/{del_id}/address",
        json={"delivery_address": new_address},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery address updated successfully"

    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        assert order is not None
        assert order.delivery_address == new_address

        tracking = (
            db.query(OrderTracking)
            .filter(OrderTracking.order_id == order_id)
            .order_by(OrderTracking.created_at.desc())
            .first()
        )
        assert tracking is not None
        assert new_address in tracking.remarks
    finally:
        db.close()


def test_update_address_delivered_fails(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="delivered")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/address",
        json={"delivery_address": "123 New Road, NY"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot update delivery address" in body["message"].lower()


def test_update_address_cancelled_fails(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="cancelled")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/address",
        json={"delivery_address": "123 New Road, NY"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert "cannot update delivery address" in body["message"].lower()


@pytest.mark.parametrize(
    "invalid_addr",
    ["", "   ", "ab", "###$$$%%%", None],
)
def test_update_address_invalid(tenant_a, invalid_addr):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.patch(
        f"/api/v1/delivery/{del_id}/address",
        json={"delivery_address": invalid_addr},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_address_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.patch(
        "/api/v1/delivery/999999/address",
        json={"delivery_address": "123 New Road, NY"},
        headers=headers,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_update_address_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    resp = client.patch(
        f"/api/v1/delivery/{del_id_a}/address",
        json={"delivery_address": "123 New Road, NY"},
        headers=headers_b,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


# ============================================================================
# 8. GET /api/v1/delivery/{delivery_id}/label (Shipping Label)
# ============================================================================

def test_get_label_success_with_customer(tenant_a):
    headers, user = tenant_a
    cust_id = create_customer_for_tenant(user, name="Alice Wonderland", phone="+1987654321")
    order_id = create_order_for_tenant(
        headers,
        user,
        order_status="confirmed",
        customer_id=cust_id,
        delivery_address="742 Evergreen Terrace, Springfield",
    )

    # Create delivery for this order
    resp_create = client.post(
        "/api/v1/delivery",
        json={
            "order_id": order_id,
            "delivery_person": "Bob Builder",
            "tracking_number": "TRK-BOB-001",
        },
        headers=headers,
    )
    assert resp_create.status_code == 201
    del_id = resp_create.json()["data"]["id"]

    resp = client.get(f"/api/v1/delivery/{del_id}/label", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery label generated successfully"

    label = body["data"]
    assert label["delivery_id"] == del_id
    assert label["order_id"] == order_id
    assert label["recipient_name"] == "Alice Wonderland"
    assert label["recipient_phone"] == "+1987654321"
    assert label["delivery_address"] == "742 Evergreen Terrace, Springfield"
    assert label["delivery_person"] == "Bob Builder"
    assert label["tracking_number"] == "TRK-BOB-001"
    assert label["status"] == "assigned"
    assert len(label["barcode"]) == 12
    assert label["barcode"].isdigit()


def test_get_label_success_without_customer(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(
        headers,
        user,
        order_status="confirmed",
        customer_id=None,
        delivery_address="Walk-in Order Depot",
    )

    resp_create = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp_create.status_code == 201
    del_id = resp_create.json()["data"]["id"]

    resp = client.get(f"/api/v1/delivery/{del_id}/label", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True

    label = body["data"]
    assert label["recipient_name"] == "Retail Customer"
    assert label["recipient_phone"] is None
    assert label["delivery_address"] == "Walk-in Order Depot"
    assert len(label["barcode"]) == 12
    assert label["barcode"].isdigit()


def test_get_label_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/999999/label", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_get_label_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    resp = client.get(f"/api/v1/delivery/{del_id_a}/label", headers=headers_b)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_get_label_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/{invalid_id}/label", headers=headers)
    assert resp.status_code == 422


# ============================================================================
# 9. GET /api/v1/delivery/{delivery_id}/tracking (Current/Latest Tracking)
# ============================================================================

def test_get_tracking_success_with_events(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user, order_status="confirmed")

    # 1. Create delivery via API (creates initial tracking record: status="pending")
    resp_create = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp_create.status_code == 201
    del_id = resp_create.json()["data"]["id"]

    # 2. Assign partner (creates second tracking record: status="assigned")
    resp_partner = client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={
            "delivery_person": "Peter Parker",
            "tracking_number": "TRK-SPIDER-007",
        },
        headers=headers,
    )
    assert resp_partner.status_code == 200

    # 3. Update status to out_for_delivery (creates third tracking record)
    resp_status = client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "out_for_delivery"},
        headers=headers,
    )
    assert resp_status.status_code == 200

    # 4. Get tracking
    resp_tracking = client.get(f"/api/v1/delivery/{del_id}/tracking", headers=headers)
    assert resp_tracking.status_code == 200
    body = resp_tracking.json()
    assert body["success"] is True
    assert body["message"] == "Delivery tracking retrieved successfully"

    data = body["data"]
    assert data["delivery_id"] == del_id
    assert data["order_id"] == order_id
    assert data["status"] == "out_for_delivery"
    assert data["delivery_person"] == "Peter Parker"
    assert data["tracking_number"] == "TRK-SPIDER-007"
    assert data["tracking_id"] is not None
    assert "out for delivery" in data["remarks"].lower()
    assert data["updated_at"] is not None


def test_get_tracking_success_no_tracking_events(tenant_a):
    headers, user = tenant_a
    del_id, order_id = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.get(f"/api/v1/delivery/{del_id}/tracking", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery tracking retrieved successfully"

    data = body["data"]
    assert data["delivery_id"] == del_id
    assert data["order_id"] == order_id
    assert data["status"] == "pending"
    assert data["delivery_person"] is None
    assert data["tracking_number"] is None
    assert data["tracking_id"] is None
    assert data["remarks"] is None
    assert data["updated_at"] is not None


def test_get_tracking_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/999999/tracking", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_get_tracking_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    resp = client.get(f"/api/v1/delivery/{del_id_a}/tracking", headers=headers_b)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_get_tracking_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/{invalid_id}/tracking", headers=headers)
    assert resp.status_code == 422


# ============================================================================
# 10. GET /api/v1/delivery/{delivery_id}/history (Status History)
# ============================================================================

def test_get_history_success_chronological_order(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user, order_status="confirmed")

    # 1. Create delivery (event 1: pending)
    resp_create = client.post(
        "/api/v1/delivery",
        json={"order_id": order_id},
        headers=headers,
    )
    assert resp_create.status_code == 201
    del_id = resp_create.json()["data"]["id"]

    # 2. Assign partner (event 2: assigned)
    client.patch(
        f"/api/v1/delivery/{del_id}/partner",
        json={"delivery_person": "Tony Stark"},
        headers=headers,
    )

    # 3. Update status (event 3: out_for_delivery)
    client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "out_for_delivery"},
        headers=headers,
    )

    # 4. Update status (event 4: delivered)
    client.patch(
        f"/api/v1/delivery/{del_id}/status",
        json={"status": "delivered"},
        headers=headers,
    )

    resp = client.get(f"/api/v1/delivery/{del_id}/history", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery history retrieved successfully"

    events = body["data"]
    assert len(events) == 4
    assert body["total"] == 4

    # Verify newest-first chronological order
    assert events[0]["status"] == "delivered"
    assert events[1]["status"] == "out_for_delivery"
    assert events[2]["status"] == "assigned"
    assert events[3]["status"] == "pending"

    # Verify fields of history item
    for item in events:
        assert item["id"] > 0
        assert item["order_id"] == order_id
        assert item["status"] is not None
        assert item["remarks"] is not None
        assert item["created_at"] is not None


def test_get_history_empty_structured_response(tenant_a):
    headers, user = tenant_a
    del_id, _ = create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.get(f"/api/v1/delivery/{del_id}/history", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "No history found for delivery"
    assert body["data"] == []
    assert body["total"] == 0


def test_get_history_not_found(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/999999/history", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


def test_get_history_cross_tenant(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    del_id_a, _ = create_delivery_for_tenant(headers_a, user_a)

    resp = client.get(f"/api/v1/delivery/{del_id_a}/history", headers=headers_b)
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["message"] == "Delivery not found"


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_get_history_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/{invalid_id}/history", headers=headers)
    assert resp.status_code == 422


# ============================================================================
# 11. GET /api/v1/delivery/stats (Delivery Statistics)
# ============================================================================

def test_get_stats_with_data(tenant_a):
    headers, user = tenant_a
    del1, _ = create_delivery_for_tenant(headers, user, initial_status="pending")
    del2, _ = create_delivery_for_tenant(headers, user, initial_status="assigned")
    del3, _ = create_delivery_for_tenant(headers, user, initial_status="delivered")

    resp = client.get("/api/v1/delivery/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery statistics retrieved successfully"

    data = body["data"]
    assert data["total_deliveries"] >= 3
    assert data["pending_deliveries"] >= 1
    assert data["assigned_deliveries"] >= 1
    assert data["delivered_deliveries"] >= 1
    assert data["out_for_delivery_deliveries"] >= 0
    assert data["cancelled_deliveries"] >= 0

    assert "total_deliveries" not in body
    assert "pending_deliveries" not in body
    assert "assigned_deliveries" not in body
    assert "delivered_deliveries" not in body
    assert "cancelled_deliveries" not in body


def test_get_stats_empty(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total_deliveries"] == 0
    assert data["pending_deliveries"] == 0
    assert data["assigned_deliveries"] == 0
    assert data["out_for_delivery_deliveries"] == 0
    assert data["delivered_deliveries"] == 0
    assert data["cancelled_deliveries"] == 0


def test_get_stats_tenant_isolation(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    create_delivery_for_tenant(headers_a, user_a, initial_status="pending")
    create_delivery_for_tenant(headers_a, user_a, initial_status="delivered")

    resp_b = client.get("/api/v1/delivery/stats", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()["data"]
    assert data_b["total_deliveries"] == 0
    assert data_b["pending_deliveries"] == 0


# ============================================================================
# 12. GET /api/v1/delivery/export (Export Deliveries)
# ============================================================================

def test_export_excel_success(tenant_a):
    headers, user = tenant_a
    create_delivery_for_tenant(headers, user, initial_status="pending")

    resp = client.get("/api/v1/delivery/export?format=excel", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "deliveries.xlsx" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 0


def test_export_csv_success(tenant_a):
    headers, user = tenant_a
    order_id = create_order_for_tenant(headers, user)
    client.post(
        "/api/v1/delivery",
        json={"order_id": order_id, "delivery_person": "Clark Kent", "tracking_number": "TRK-SUPER-001"},
        headers=headers,
    )

    resp = client.get("/api/v1/delivery/export?format=csv", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "deliveries.csv" in resp.headers.get("content-disposition", "")
    content_text = resp.text
    assert "ID,Order Number,Status,Delivery Person,Tracking Number" in content_text
    assert "Clark Kent" in content_text
    assert "TRK-SUPER-001" in content_text


def test_export_status_filter(tenant_a):
    headers, user = tenant_a
    create_delivery_for_tenant(headers, user, initial_status="pending")
    create_delivery_for_tenant(headers, user, initial_status="delivered")

    resp = client.get("/api/v1/delivery/export?format=csv&status=delivered", headers=headers)
    assert resp.status_code == 200
    content_text = resp.text
    assert "delivered" in content_text


def test_export_tenant_isolation(tenant_a, tenant_b):
    headers_a, user_a = tenant_a
    headers_b, _ = tenant_b

    order_id = create_order_for_tenant(headers_a, user_a)
    client.post(
        "/api/v1/delivery",
        json={"order_id": order_id, "delivery_person": "Bruce Wayne", "tracking_number": "TRK-BATMAN-999"},
        headers=headers_a,
    )

    resp_b = client.get("/api/v1/delivery/export?format=csv", headers=headers_b)
    assert resp_b.status_code == 200
    assert "TRK-BATMAN-999" not in resp_b.text
    assert "Bruce Wayne" not in resp_b.text


def test_export_empty_data(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/export?format=csv", headers=headers)
    assert resp.status_code == 200
    assert "ID,Order Number,Status,Delivery Person" in resp.text


@pytest.mark.parametrize("invalid_format", ["pdf", "json", "xml", "", "   ", "xlsx"])
def test_export_invalid_format(tenant_a, invalid_format):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/export?format={invalid_format}", headers=headers)
    assert resp.status_code == 422


@pytest.mark.parametrize("invalid_status", ["unknown_status", "invalid", "", "   ", "123"])
def test_export_invalid_status(tenant_a, invalid_status):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/export?status={invalid_status}", headers=headers)
    assert resp.status_code == 422


# =====================================================================
# Phase 4: Delivery Methods APIs Tests
# =====================================================================

def test_list_delivery_methods_empty(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/methods", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "No delivery methods found"
    assert data["data"] == []
    assert data["total"] == 0


def test_create_delivery_method_minimal(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Standard Ground",
        "code": "standard_ground",
        "description": "Standard ground delivery",
    }
    resp = client.post("/api/v1/delivery/methods", json=payload, headers=headers)
    assert resp.status_code == 201
    res = resp.json()
    assert res["success"] is True
    assert res["message"] == "Delivery method created successfully"
    method = res["data"]
    assert method["name"] == "Standard Ground"
    assert method["code"] == "STANDARD_GROUND"
    assert float(method["cost"]) == 0.0
    assert method["is_active"] is True
    assert method["description"] is not None
    assert method["estimated_days"] is None
    assert method["id"] > 0
    assert method["created_at"] is not None


def test_create_delivery_method_full(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Express Priority",
        "code": "EXP-PRIO",
        "description": "Next business day courier delivery",
        "cost": 29.99,
        "estimated_days": 1,
        "is_active": True,
    }
    resp = client.post("/api/v1/delivery/methods", json=payload, headers=headers)
    assert resp.status_code == 201
    method = resp.json()["data"]
    assert method["name"] == "Express Priority"
    assert method["code"] == "EXP-PRIO"
    assert method["description"] == "Next business day courier delivery"
    assert float(method["cost"]) == 29.99
    assert method["estimated_days"] == 1
    assert method["is_active"] is True


def test_create_delivery_method_duplicate_code_conflict(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Same Day Delivery",
        "code": "SAME_DAY_CONF",
        "description": "Same day delivery",
    }
    resp1 = client.post("/api/v1/delivery/methods", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Attempt duplicate in same tenant
    resp2 = client.post("/api/v1/delivery/methods", json=payload, headers=headers)
    assert resp2.status_code == 409
    err = resp2.json()
    assert "already exists" in (err.get("message") or err.get("detail") or str(err))


def test_create_delivery_method_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b
    payload = {
        "name": "Shared Code Method",
        "code": "SHARED_CODE_1",
        "description": "Shared code delivery",
    }
    # Both tenants can have identical codes without conflict
    resp_a = client.post("/api/v1/delivery/methods", json=payload, headers=headers_a)
    assert resp_a.status_code == 201

    resp_b = client.post("/api/v1/delivery/methods", json=payload, headers=headers_b)
    assert resp_b.status_code == 201

    # List of Tenant A should only contain Tenant A's methods
    list_a = client.get("/api/v1/delivery/methods", headers=headers_a).json()["data"]
    ids_a = [m["id"] for m in list_a]
    assert resp_a.json()["data"]["id"] in ids_a
    assert resp_b.json()["data"]["id"] not in ids_a

    # List of Tenant B should only contain Tenant B's methods
    list_b = client.get("/api/v1/delivery/methods", headers=headers_b).json()["data"]
    ids_b = [m["id"] for m in list_b]
    assert resp_b.json()["data"]["id"] in ids_b
    assert resp_a.json()["data"]["id"] not in ids_b


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "A"),
        ("name", "$$$@@@"),
        ("code", ""),
        ("code", "   "),
        ("code", "C"),
        ("code", "CODE WITH SPACES"),
        ("code", "CODE#SPECIAL!"),
        ("cost", -10),
        ("cost", -0.01),
        ("cost", "invalid_cost"),
        ("estimated_days", -1),
        ("estimated_days", "invalid_days"),
    ],
)
def test_create_delivery_method_validation_errors(tenant_a, field, value):
    headers, _ = tenant_a
    payload = {
        "name": "Valid Name",
        "code": "VALID_CODE",
        "description": "Valid method description",
        "cost": 10.0,
        "estimated_days": 2,
    }
    payload[field] = value
    resp = client.post("/api/v1/delivery/methods", json=payload, headers=headers)
    assert resp.status_code == 422


def test_list_delivery_methods_filter_is_active(tenant_a):
    headers, _ = tenant_a
    # Create one active and one inactive method
    p_act = {"name": "Active Courier", "code": "ACT_METH_1", "description": "Active courier", "is_active": True}
    p_inact = {"name": "Inactive Courier", "code": "INACT_METH_1", "description": "Inactive courier", "is_active": False}

    r1 = client.post("/api/v1/delivery/methods", json=p_act, headers=headers)
    assert r1.status_code == 201
    id_act = r1.json()["data"]["id"]

    r2 = client.post("/api/v1/delivery/methods", json=p_inact, headers=headers)
    assert r2.status_code == 201
    id_inact = r2.json()["data"]["id"]

    # Filter active
    resp_act = client.get("/api/v1/delivery/methods?is_active=true", headers=headers)
    assert resp_act.status_code == 200
    ids_active = [m["id"] for m in resp_act.json()["data"]]
    assert id_act in ids_active
    assert id_inact not in ids_active

    # Filter inactive
    resp_inact = client.get("/api/v1/delivery/methods?is_active=false", headers=headers)
    assert resp_inact.status_code == 200
    ids_inactive = [m["id"] for m in resp_inact.json()["data"]]
    assert id_inact in ids_inactive
    assert id_act not in ids_inactive

    # No filter returns both
    resp_all = client.get("/api/v1/delivery/methods", headers=headers)
    assert resp_all.status_code == 200
    ids_all = [m["id"] for m in resp_all.json()["data"]]
    assert id_act in ids_all
    assert id_inact in ids_all


def test_update_delivery_method_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Initial Name", "code": "INIT_CODE", "description": "Initial description", "cost": 5.0, "estimated_days": 3},
        headers=headers,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    update_payload = {
        "name": "Updated Name",
        "code": "UPDATED_CODE",
        "description": "Updated description",
        "cost": 12.50,
        "estimated_days": 2,
        "is_active": False,
    }
    update_resp = client.put(
        f"/api/v1/delivery/methods/{method_id}",
        json=update_payload,
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["name"] == "Updated Name"
    assert updated["code"] == "UPDATED_CODE"
    assert updated["description"] == "Updated description"
    assert float(updated["cost"]) == 12.50
    assert updated["estimated_days"] == 2
    assert updated["is_active"] is False


def test_update_delivery_method_duplicate_code_conflict(tenant_a):
    headers, _ = tenant_a
    r1 = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Method One", "code": "METHOD_ONE_CODE", "description": "Method one desc"},
        headers=headers,
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Method Two", "code": "METHOD_TWO_CODE", "description": "Method two desc"},
        headers=headers,
    )
    assert r2.status_code == 201
    m2_id = r2.json()["data"]["id"]

    # Trying to update Method 2 to use Method 1's code should trigger 409
    resp_conflict = client.put(
        f"/api/v1/delivery/methods/{m2_id}",
        json={"code": "METHOD_ONE_CODE"},
        headers=headers,
    )
    assert resp_conflict.status_code == 409

    # Updating Method 2 with its own code should succeed
    resp_self = client.put(
        f"/api/v1/delivery/methods/{m2_id}",
        json={"code": "METHOD_TWO_CODE", "name": "Method Two Renamed"},
        headers=headers,
    )
    assert resp_self.status_code == 200
    assert resp_self.json()["data"]["name"] == "Method Two Renamed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "X"),
        ("code", ""),
        ("code", "   "),
        ("code", "X"),
        ("code", "CODE WITH SPACES"),
        ("cost", -1),
        ("estimated_days", -5),
    ],
)
def test_update_delivery_method_validation_errors(tenant_a, field, value):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Method For Validation", "code": "VAL_CODE_UPD", "description": "Validation description"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    resp = client.put(
        f"/api/v1/delivery/methods/{method_id}",
        json={field: value},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_delivery_method_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Tenant A Method", "code": "T_A_METH_UPD", "description": "Tenant A description"},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.put(
        "/api/v1/delivery/methods/9999999",
        json={"name": "Does Not Exist"},
        headers=headers_a,
    )
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.put(
        f"/api/v1/delivery/methods/{method_id}",
        json={"name": "Hacked Method"},
        headers=headers_b,
    )
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_update_delivery_method_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.put(
        f"/api/v1/delivery/methods/{invalid_id}",
        json={"name": "New Name"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_toggle_delivery_method_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Toggle Test Method", "code": "TOGGLE_METH_1", "description": "Toggle description", "is_active": True},
        headers=headers,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    # Toggle 1: True -> False
    toggle_1 = client.patch(f"/api/v1/delivery/methods/{method_id}/toggle", headers=headers)
    assert toggle_1.status_code == 200
    assert toggle_1.json()["data"]["is_active"] is False

    # Toggle 2: False -> True
    toggle_2 = client.patch(f"/api/v1/delivery/methods/{method_id}/toggle", headers=headers)
    assert toggle_2.status_code == 200
    assert toggle_2.json()["data"]["is_active"] is True


def test_toggle_delivery_method_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Toggle Tenant A", "code": "TOG_T_A", "description": "Toggle description"},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.patch("/api/v1/delivery/methods/9999999/toggle", headers=headers_a)
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.patch(f"/api/v1/delivery/methods/{method_id}/toggle", headers=headers_b)
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_toggle_delivery_method_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.patch(f"/api/v1/delivery/methods/{invalid_id}/toggle", headers=headers)
    assert resp.status_code == 422


def test_delete_delivery_method_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Method To Delete", "code": "DEL_METH_1", "description": "Delete description"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    del_resp = client.delete(f"/api/v1/delivery/methods/{method_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert del_resp.json()["message"] == "Delivery method deleted successfully"

    # Subsequent update / toggle / delete returns 404
    assert client.put(f"/api/v1/delivery/methods/{method_id}", json={"name": "abc"}, headers=headers).status_code == 404
    assert client.patch(f"/api/v1/delivery/methods/{method_id}/toggle", headers=headers).status_code == 404
    assert client.delete(f"/api/v1/delivery/methods/{method_id}", headers=headers).status_code == 404


def test_delete_delivery_method_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/methods",
        json={"name": "Delete Tenant A", "code": "DEL_T_A", "description": "Delete description"},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    method_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.delete("/api/v1/delivery/methods/9999999", headers=headers_a)
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.delete(f"/api/v1/delivery/methods/{method_id}", headers=headers_b)
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_delete_delivery_method_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.delete(f"/api/v1/delivery/methods/{invalid_id}", headers=headers)
    assert resp.status_code == 422


# =====================================================================
# Phase 5: Delivery Zones APIs Tests
# =====================================================================

def test_list_delivery_zones_empty(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/zones", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "No delivery zones found"
    assert data["data"] == []
    assert data["total"] == 0


def test_create_delivery_zone_minimal(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "South Mumbai Zone",
        "code": "mum_south",
        "description": "South Mumbai zone desc",
        "pincodes": ["400001", "400002"],
    }
    resp = client.post("/api/v1/delivery/zones", json=payload, headers=headers)
    assert resp.status_code == 201
    res = resp.json()
    assert res["success"] is True
    assert res["message"] == "Delivery zone created successfully"
    zone = res["data"]
    assert zone["name"] == "South Mumbai Zone"
    assert zone["code"] == "MUM_SOUTH"
    assert zone["pincodes"] == ["400001", "400002"]
    assert zone["is_active"] is True
    assert zone["description"] is not None
    assert zone["city"] is None
    assert zone["state"] is None
    assert zone["id"] > 0
    assert zone["created_at"] is not None


def test_create_delivery_zone_full(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Pune West Zone",
        "code": "PUN_WEST",
        "description": "West Pune delivery belt",
        "city": "Pune",
        "state": "Maharashtra",
        "pincodes": ["411001", "411004", "411038"],
        "is_active": True,
    }
    resp = client.post("/api/v1/delivery/zones", json=payload, headers=headers)
    assert resp.status_code == 201
    zone = resp.json()["data"]
    assert zone["name"] == "Pune West Zone"
    assert zone["code"] == "PUN_WEST"
    assert zone["description"] == "West Pune delivery belt"
    assert zone["city"] == "Pune"
    assert zone["state"] == "Maharashtra"
    assert zone["pincodes"] == ["411001", "411004", "411038"]
    assert zone["is_active"] is True


def test_create_delivery_zone_duplicate_code_conflict(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Central Mumbai Zone",
        "code": "MUM_CENTRAL_CONF",
        "description": "Central Mumbai zone description",
        "pincodes": ["400012", "400013"],
    }
    resp1 = client.post("/api/v1/delivery/zones", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Attempt duplicate code in same tenant
    resp2 = client.post("/api/v1/delivery/zones", json=payload, headers=headers)
    assert resp2.status_code == 409
    err = resp2.json()
    assert "already exists" in (err.get("message") or err.get("detail") or str(err))


def test_create_delivery_zone_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b
    payload = {
        "name": "Shared Zone Name",
        "code": "SHARED_ZONE_1",
        "description": "Shared zone description",
        "pincodes": ["400050"],
    }
    # Both tenants can have identical zone codes
    resp_a = client.post("/api/v1/delivery/zones", json=payload, headers=headers_a)
    assert resp_a.status_code == 201

    resp_b = client.post("/api/v1/delivery/zones", json=payload, headers=headers_b)
    assert resp_b.status_code == 201

    # Tenant A sees only its own zone
    list_a = client.get("/api/v1/delivery/zones", headers=headers_a).json()["data"]
    ids_a = [z["id"] for z in list_a]
    assert resp_a.json()["data"]["id"] in ids_a
    assert resp_b.json()["data"]["id"] not in ids_a

    # Tenant B sees only its own zone
    list_b = client.get("/api/v1/delivery/zones", headers=headers_b).json()["data"]
    ids_b = [z["id"] for z in list_b]
    assert resp_b.json()["data"]["id"] in ids_b
    assert resp_a.json()["data"]["id"] not in ids_b


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "A"),
        ("name", "12345"),
        ("code", ""),
        ("code", "   "),
        ("code", "ZONE WITH SPACES"),
        ("code", "ZONE#SPECIAL!"),
        ("pincodes", []),
        ("pincodes", ["12345"]),
        ("pincodes", ["1234567"]),
        ("pincodes", ["ABCDEF"]),
        ("pincodes", ["000000"]),
        ("pincodes", [-40001]),
    ],
)
def test_create_delivery_zone_validation_errors(tenant_a, field, value):
    headers, _ = tenant_a
    payload = {
        "name": "Valid Zone Name",
        "code": "VALID_ZONE_CODE",
        "pincodes": ["400001"],
    }
    payload[field] = value
    resp = client.post("/api/v1/delivery/zones", json=payload, headers=headers)
    assert resp.status_code == 422


def test_list_delivery_zones_filter_is_active(tenant_a):
    headers, _ = tenant_a
    p_act = {"name": "Active Zone", "code": "ACT_ZONE_1", "description": "Active zone desc", "pincodes": ["400001"], "is_active": True}
    p_inact = {"name": "Inactive Zone", "code": "INACT_ZONE_1", "description": "Inactive zone desc", "pincodes": ["400002"], "is_active": False}

    r1 = client.post("/api/v1/delivery/zones", json=p_act, headers=headers)
    assert r1.status_code == 201
    id_act = r1.json()["data"]["id"]

    r2 = client.post("/api/v1/delivery/zones", json=p_inact, headers=headers)
    assert r2.status_code == 201
    id_inact = r2.json()["data"]["id"]

    # Filter active
    resp_act = client.get("/api/v1/delivery/zones?is_active=true", headers=headers)
    assert resp_act.status_code == 200
    ids_active = [z["id"] for z in resp_act.json()["data"]]
    assert id_act in ids_active
    assert id_inact not in ids_active

    # Filter inactive
    resp_inact = client.get("/api/v1/delivery/zones?is_active=false", headers=headers)
    assert resp_inact.status_code == 200
    ids_inactive = [z["id"] for z in resp_inact.json()["data"]]
    assert id_inact in ids_inactive
    assert id_act not in ids_inactive

    # No filter returns both
    resp_all = client.get("/api/v1/delivery/zones", headers=headers)
    assert resp_all.status_code == 200
    ids_all = [z["id"] for z in resp_all.json()["data"]]
    assert id_act in ids_all
    assert id_inact in ids_all


def test_update_delivery_zone_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Initial Zone", "code": "INIT_ZONE", "description": "Initial zone desc", "pincodes": ["400001"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    zone_id = create_resp.json()["data"]["id"]

    update_payload = {
        "name": "Updated Zone Name",
        "code": "UPDATED_ZONE_CODE",
        "description": "Updated belt description",
        "city": "Thane",
        "state": "Maharashtra",
        "pincodes": ["400601", "400602"],
        "is_active": False,
    }
    update_resp = client.put(
        f"/api/v1/delivery/zones/{zone_id}",
        json=update_payload,
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["name"] == "Updated Zone Name"
    assert updated["code"] == "UPDATED_ZONE_CODE"
    assert updated["description"] == "Updated belt description"
    assert updated["city"] == "Thane"
    assert updated["state"] == "Maharashtra"
    assert updated["pincodes"] == ["400601", "400602"]
    assert updated["is_active"] is False


def test_update_delivery_zone_duplicate_code_conflict(tenant_a):
    headers, _ = tenant_a
    r1 = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone One", "code": "ZONE_ONE_CODE", "description": "Zone one desc", "pincodes": ["400001"]},
        headers=headers,
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone Two", "code": "ZONE_TWO_CODE", "description": "Zone two desc", "pincodes": ["400002"]},
        headers=headers,
    )
    assert r2.status_code == 201
    z2_id = r2.json()["data"]["id"]

    # Updating Zone 2 to Zone 1's code -> 409
    resp_conflict = client.put(
        f"/api/v1/delivery/zones/{z2_id}",
        json={"code": "ZONE_ONE_CODE"},
        headers=headers,
    )
    assert resp_conflict.status_code == 409

    # Updating Zone 2 with its own code -> 200
    resp_self = client.put(
        f"/api/v1/delivery/zones/{z2_id}",
        json={"code": "ZONE_TWO_CODE", "name": "Zone Two Renamed"},
        headers=headers,
    )
    assert resp_self.status_code == 200
    assert resp_self.json()["data"]["name"] == "Zone Two Renamed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "X"),
        ("name", "99999"),
        ("code", ""),
        ("code", "   "),
        ("code", "X"),
        ("code", "CODE WITH SPACES"),
        ("pincodes", ["invalid"]),
        ("pincodes", ["123"]),
    ],
)
def test_update_delivery_zone_validation_errors(tenant_a, field, value):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone For Validation", "code": "VAL_ZONE_UPD", "description": "Validation zone description", "pincodes": ["400001"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    zone_id = create_resp.json()["data"]["id"]

    resp = client.put(
        f"/api/v1/delivery/zones/{zone_id}",
        json={field: value},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_delivery_zone_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Tenant A Zone", "code": "T_A_ZONE_UPD", "description": "Tenant A zone description", "pincodes": ["400001"]},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    zone_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.put(
        "/api/v1/delivery/zones/9999999",
        json={"name": "Does Not Exist"},
        headers=headers_a,
    )
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.put(
        f"/api/v1/delivery/zones/{zone_id}",
        json={"name": "Hacked Zone"},
        headers=headers_b,
    )
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_update_delivery_zone_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.put(
        f"/api/v1/delivery/zones/{invalid_id}",
        json={"name": "New Name"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_delete_delivery_zone_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone To Delete", "code": "DEL_ZONE_1", "description": "Delete zone description", "pincodes": ["400001"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    zone_id = create_resp.json()["data"]["id"]

    del_resp = client.delete(f"/api/v1/delivery/zones/{zone_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert del_resp.json()["message"] == "Delivery zone deleted successfully"

    # Subsequent update / delete returns 404
    assert client.put(f"/api/v1/delivery/zones/{zone_id}", json={"name": "abc"}, headers=headers).status_code == 404
    assert client.delete(f"/api/v1/delivery/zones/{zone_id}", headers=headers).status_code == 404


def test_delete_delivery_zone_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Delete Tenant A Zone", "code": "DEL_T_A_ZONE", "description": "Delete tenant A zone description", "pincodes": ["400001"]},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    zone_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.delete("/api/v1/delivery/zones/9999999", headers=headers_a)
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.delete(f"/api/v1/delivery/zones/{zone_id}", headers=headers_b)
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_delete_delivery_zone_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.delete(f"/api/v1/delivery/zones/{invalid_id}", headers=headers)
    assert resp.status_code == 422


# ==============================================================================
# PHASE 6: DELIVERY PARTNERS TESTS
# ==============================================================================


def test_list_delivery_partners_empty(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/partners", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert body["data"] == []
    assert body["total"] == 0


def test_connect_delivery_partner_minimal(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "BlueDart Express",
        "code": "BLUEDART",
        "description": "Express logistics partner",
    }
    resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Delivery partner connected successfully"
    partner = body["data"]
    assert partner["name"] == "BlueDart Express"
    assert partner["code"] == "BLUEDART"
    assert partner["is_active"] is True
    assert "api_key" not in partner
    assert "api_secret" not in partner


def test_connect_delivery_partner_full(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Delhivery Logistics",
        "code": "DELHIVERY",
        "description": "Pan-India express logistics partner",
        "contact_email": "ops@delhivery.com",
        "contact_phone": "+919876543210",
        "api_key": "secret_api_key_123",
        "api_secret": "secret_api_token_456",
        "tracking_url_template": "https://delhivery.com/track/{tracking_number}",
        "is_active": True,
    }
    resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
    assert resp.status_code == 201
    partner = resp.json()["data"]
    assert partner["name"] == "Delhivery Logistics"
    assert partner["code"] == "DELHIVERY"
    assert partner["description"] == "Pan-India express logistics partner"
    assert partner["contact_email"] == "ops@delhivery.com"
    assert partner["contact_phone"] == "+919876543210"
    assert partner["tracking_url_template"] == "https://delhivery.com/track/{tracking_number}"
    assert partner["is_active"] is True
    assert "api_key" not in partner
    assert "api_secret" not in partner


def test_connect_delivery_partner_duplicate_code_conflict(tenant_a):
    headers, _ = tenant_a
    payload = {
        "name": "Shadowfax Tech",
        "code": "SHADOWFAX",
        "description": "Shadowfax logistics partner",
    }
    resp1 = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
    assert resp2.status_code == 409
    err = resp2.json()
    assert "already exists" in (err.get("message") or err.get("detail") or str(err))


def test_connect_delivery_partner_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b
    payload = {
        "name": "Shared Courier Partner",
        "code": "SHARED_COURIER",
        "description": "Shared courier partner description",
    }
    resp_a = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers_a)
    assert resp_a.status_code == 201

    resp_b = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers_b)
    assert resp_b.status_code == 201

    list_a = client.get("/api/v1/delivery/partners", headers=headers_a).json()["data"]
    ids_a = [p["id"] for p in list_a]
    assert resp_a.json()["data"]["id"] in ids_a
    assert resp_b.json()["data"]["id"] not in ids_a

    list_b = client.get("/api/v1/delivery/partners", headers=headers_b).json()["data"]
    ids_b = [p["id"] for p in list_b]
    assert resp_b.json()["data"]["id"] in ids_b
    assert resp_a.json()["data"]["id"] not in ids_b


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "A"),
        ("name", "12345"),
        ("code", ""),
        ("code", "   "),
        ("code", "PARTNER WITH SPACES"),
        ("code", "PARTNER#SPECIAL!"),
        ("contact_email", "not-an-email"),
        ("contact_email", "@domain.com"),
        ("contact_phone", "invalid-phone-letters"),
    ],
)
def test_connect_delivery_partner_validation_errors(tenant_a, field, value):
    headers, _ = tenant_a
    payload = {
        "name": "Valid Partner",
        "code": "VALID_CODE",
        "description": "Valid partner description",
    }
    payload[field] = value
    resp = client.post("/api/v1/delivery/partners/connect", json=payload, headers=headers)
    assert resp.status_code == 422


def test_list_delivery_partners_filter_is_active(tenant_a):
    headers, _ = tenant_a
    p_act = {"name": "Active Partner", "code": "ACT_PARTNER_1", "description": "Active partner description", "is_active": True}
    p_inact = {"name": "Inactive Partner", "code": "INACT_PARTNER_1", "description": "Inactive partner description", "is_active": False}

    r1 = client.post("/api/v1/delivery/partners/connect", json=p_act, headers=headers)
    assert r1.status_code == 201
    id_act = r1.json()["data"]["id"]

    r2 = client.post("/api/v1/delivery/partners/connect", json=p_inact, headers=headers)
    assert r2.status_code == 201
    id_inact = r2.json()["data"]["id"]

    # Filter active
    resp_act = client.get("/api/v1/delivery/partners?is_active=true", headers=headers)
    assert resp_act.status_code == 200
    ids_active = [p["id"] for p in resp_act.json()["data"]]
    assert id_act in ids_active
    assert id_inact not in ids_active

    # Filter inactive
    resp_inact = client.get("/api/v1/delivery/partners?is_active=false", headers=headers)
    assert resp_inact.status_code == 200
    ids_inactive = [p["id"] for p in resp_inact.json()["data"]]
    assert id_inact in ids_inactive
    assert id_act not in ids_inactive

    # Without filter returns both
    resp_all = client.get("/api/v1/delivery/partners", headers=headers)
    assert resp_all.status_code == 200
    ids_all = [p["id"] for p in resp_all.json()["data"]]
    assert id_act in ids_all
    assert id_inact in ids_all


@pytest.mark.parametrize(
    "invalid_active",
    [
        "invalid",
        "abc",
        "maybe",
        "2",
        "-1",
        "yes_no",
        "",
    ],
)
def test_list_delivery_partners_filter_is_active_invalid_returns_422(tenant_a, invalid_active):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/partners?is_active={invalid_active}", headers=headers)
    assert resp.status_code == 422


def test_update_delivery_partner_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Initial Partner", "code": "INIT_PARTNER", "description": "Initial partner description"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    partner_id = create_resp.json()["data"]["id"]

    update_payload = {
        "name": "Updated Partner Name",
        "code": "UPD_PARTNER_CODE",
        "description": "Updated partner description",
        "contact_email": "updated@partner.com",
        "contact_phone": "+919988776655",
        "api_key": "new_api_key",
        "api_secret": "new_api_secret",
        "tracking_url_template": "https://newtrack.com/{tracking_number}",
        "is_active": False,
    }
    update_resp = client.put(
        f"/api/v1/delivery/partners/{partner_id}",
        json=update_payload,
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["name"] == "Updated Partner Name"
    assert updated["code"] == "UPD_PARTNER_CODE"
    assert updated["description"] == "Updated partner description"
    assert updated["contact_email"] == "updated@partner.com"
    assert updated["contact_phone"] == "+919988776655"
    assert updated["tracking_url_template"] == "https://newtrack.com/{tracking_number}"
    assert updated["is_active"] is False
    assert "api_key" not in updated
    assert "api_secret" not in updated


def test_update_delivery_partner_empty_body_rejected_with_422(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Partner For Empty Put", "code": "EMPTY_PUT_TEST", "description": "Partner description"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    partner_id = create_resp.json()["data"]["id"]

    # Attempt PUT with {}
    resp = client.put(
        f"/api/v1/delivery/partners/{partner_id}",
        json={},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_delivery_partner_duplicate_code_conflict(tenant_a):
    headers, _ = tenant_a
    r1 = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Partner One", "code": "PARTNER_ONE_CODE", "description": "Partner one desc"},
        headers=headers,
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Partner Two", "code": "PARTNER_TWO_CODE", "description": "Partner two desc"},
        headers=headers,
    )
    assert r2.status_code == 201
    p2_id = r2.json()["data"]["id"]

    # Updating Partner 2 to Partner 1's code -> 409
    resp_conflict = client.put(
        f"/api/v1/delivery/partners/{p2_id}",
        json={"code": "PARTNER_ONE_CODE"},
        headers=headers,
    )
    assert resp_conflict.status_code == 409

    # Updating Partner 2 with its own code -> 200
    resp_self = client.put(
        f"/api/v1/delivery/partners/{p2_id}",
        json={"code": "PARTNER_TWO_CODE", "name": "Partner Two Renamed"},
        headers=headers,
    )
    assert resp_self.status_code == 200
    assert resp_self.json()["data"]["name"] == "Partner Two Renamed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "X"),
        ("name", "99999"),
        ("code", ""),
        ("code", "   "),
        ("code", "X"),
        ("code", "CODE WITH SPACES"),
        ("contact_email", "invalid-email"),
        ("contact_phone", "invalid-phone"),
    ],
)
def test_update_delivery_partner_validation_errors(tenant_a, field, value):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Partner For Validation", "code": "VAL_PARTNER_UPD", "description": "Validation partner description"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    partner_id = create_resp.json()["data"]["id"]

    resp = client.put(
        f"/api/v1/delivery/partners/{partner_id}",
        json={field: value},
        headers=headers,
    )
    assert resp.status_code == 422


def test_update_delivery_partner_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Tenant A Partner", "code": "T_A_PARTNER_UPD", "description": "Tenant A partner description"},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    partner_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.put(
        "/api/v1/delivery/partners/9999999",
        json={"name": "Does Not Exist"},
        headers=headers_a,
    )
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.put(
        f"/api/v1/delivery/partners/{partner_id}",
        json={"name": "Hacked Partner"},
        headers=headers_b,
    )
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_update_delivery_partner_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.put(
        f"/api/v1/delivery/partners/{invalid_id}",
        json={"name": "New Name"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_delete_delivery_partner_success(tenant_a):
    headers, _ = tenant_a
    create_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Partner To Delete", "code": "DEL_PARTNER_1", "description": "Delete partner description"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    partner_id = create_resp.json()["data"]["id"]

    del_resp = client.delete(f"/api/v1/delivery/partners/{partner_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert del_resp.json()["message"] == "Delivery partner deleted successfully"

    # Subsequent update / delete returns 404
    assert client.put(f"/api/v1/delivery/partners/{partner_id}", json={"name": "abc"}, headers=headers).status_code == 404
    assert client.delete(f"/api/v1/delivery/partners/{partner_id}", headers=headers).status_code == 404


def test_delete_delivery_partner_not_found_and_cross_tenant(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    create_resp = client.post(
        "/api/v1/delivery/partners/connect",
        json={"name": "Delete Tenant A Partner", "code": "DEL_T_A_PARTNER", "description": "Delete tenant A partner description"},
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    partner_id = create_resp.json()["data"]["id"]

    # Non-existent ID
    resp_404 = client.delete("/api/v1/delivery/partners/9999999", headers=headers_a)
    assert resp_404.status_code == 404

    # Cross-tenant ID
    resp_cross = client.delete(f"/api/v1/delivery/partners/{partner_id}", headers=headers_b)
    assert resp_cross.status_code == 404


@pytest.mark.parametrize("invalid_id", [0, -1, "abc", 12.34])
def test_delete_delivery_partner_invalid_id(tenant_a, invalid_id):
    headers, _ = tenant_a
    resp = client.delete(f"/api/v1/delivery/partners/{invalid_id}", headers=headers)
    assert resp.status_code == 422


# ==============================================================================
# PHASE 7: PINCODE SERVICEABILITY TESTS
# ==============================================================================


def test_check_serviceability_serviceable(tenant_a):
    headers, _ = tenant_a
    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "South Mumbai Serv", "code": "MUM_SERV_1", "description": "South Mumbai serv zone", "pincodes": ["400001", "400005"], "is_active": True},
        headers=headers,
    )
    assert z_resp.status_code == 201

    resp = client.get("/api/v1/delivery/serviceability/400001", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Pincode is serviceable"
    data = body["data"]
    assert data["pincode"] == "400001"
    assert data["is_serviceable"] is True
    assert data["zone_code"] == "MUM_SERV_1"
    assert data["zone_name"] == "South Mumbai Serv"


def test_check_serviceability_non_serviceable(tenant_a):
    headers, _ = tenant_a
    resp = client.get("/api/v1/delivery/serviceability/499999", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Pincode is not serviceable"
    data = body["data"]
    assert data["pincode"] == "499999"
    assert data["is_serviceable"] is False
    assert data["zone_id"] is None
    assert data["zone_code"] is None
    assert data["zone_name"] is None


def test_check_serviceability_inactive_zone(tenant_a):
    headers, _ = tenant_a
    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Inactive Zone Serv", "code": "INACT_SERV_1", "description": "Inactive serv zone", "pincodes": ["411099"], "is_active": False},
        headers=headers,
    )
    assert z_resp.status_code == 201

    resp = client.get("/api/v1/delivery/serviceability/411099", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["is_serviceable"] is False


@pytest.mark.parametrize(
    "invalid_pincode",
    [
        "12345",
        "1234567",
        "ABCDEF",
        "400.01",
        "400@01",
        "-40001",
        "000000",
        " 40001",
        "40001 ",
    ],
)
def test_check_serviceability_validation_errors(tenant_a, invalid_pincode):
    headers, _ = tenant_a
    resp = client.get(f"/api/v1/delivery/serviceability/{invalid_pincode}", headers=headers)
    assert resp.status_code == 422


def test_check_serviceability_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Tenant A Exclusive Zone", "code": "T_A_EXCL", "description": "Tenant A excl zone", "pincodes": ["422001"], "is_active": True},
        headers=headers_a,
    )
    assert z_resp.status_code == 201

    resp_a = client.get("/api/v1/delivery/serviceability/422001", headers=headers_a)
    assert resp_a.status_code == 200
    assert resp_a.json()["data"]["is_serviceable"] is True

    resp_b = client.get("/api/v1/delivery/serviceability/422001", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json()["data"]["is_serviceable"] is False


def test_upload_serviceability_csv_success(tenant_a):
    headers, _ = tenant_a
    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "CSV Target Zone", "code": "CSV_TARGET", "description": "CSV target zone", "pincodes": ["400010"]},
        headers=headers,
    )
    assert z_resp.status_code == 201

    csv_content = "zone_code,pincode\nCSV_TARGET,400010\nCSV_TARGET,400020\nCSV_TARGET,400030\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}

    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "Pincodes uploaded successfully"
    data = body["data"]
    assert data["total_rows_processed"] == 3
    assert data["pincodes_added"] == 2
    assert data["pincodes_existing"] == 1
    assert "CSV_TARGET" in data["zones_updated"]

    get_resp = client.get("/api/v1/delivery/serviceability/400020", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["is_serviceable"] is True
    assert get_resp.json()["data"]["zone_code"] == "CSV_TARGET"


def test_upload_serviceability_excel_success(tenant_a):
    headers, _ = tenant_a
    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Excel Target Zone", "code": "XLSX_TARGET", "description": "Excel target zone", "pincodes": ["400050"]},
        headers=headers,
    )
    assert z_resp.status_code == 201

    wb = Workbook()
    ws = wb.active
    ws.append(["zone_code", "pincode"])
    ws.append(["XLSX_TARGET", "400050"])
    ws.append(["XLSX_TARGET", "400060"])
    ws.append(["XLSX_TARGET", "400070"])
    buf = io.BytesIO()
    wb.save(buf)
    excel_bytes = buf.getvalue()

    files = {"file": ("pincodes.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_rows_processed"] == 3
    assert data["pincodes_added"] == 2
    assert data["pincodes_existing"] == 1
    assert "XLSX_TARGET" in data["zones_updated"]

    get_resp = client.get("/api/v1/delivery/serviceability/400060", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["is_serviceable"] is True


def test_upload_serviceability_missing_file(tenant_a):
    headers, _ = tenant_a
    resp = client.post("/api/v1/delivery/serviceability/upload", headers=headers)
    assert resp.status_code == 422


def test_upload_serviceability_empty_file(tenant_a):
    headers, _ = tenant_a
    files = {"file": ("empty.csv", b"", "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 422
    assert "empty" in resp.text.lower()


@pytest.mark.parametrize(
    "bad_filename,bad_content",
    [
        ("data.txt", b"zone_code,pincode\nZ1,400001\n"),
        ("data.json", b"{}"),
        ("data.pdf", b"%PDF-1.4"),
        ("data.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    ],
)
def test_upload_serviceability_unsupported_format(tenant_a, bad_filename, bad_content):
    headers, _ = tenant_a
    files = {"file": (bad_filename, bad_content, "application/octet-stream")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 422
    assert "unsupported file format" in resp.text.lower()


def test_upload_serviceability_missing_headers(tenant_a):
    headers, _ = tenant_a
    csv_missing_col = "zone_code,city\nZONE_1,Mumbai\n"
    files = {"file": ("pincodes.csv", csv_missing_col.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 422
    assert "missing required columns" in resp.text.lower()


def test_upload_serviceability_unknown_zone_code(tenant_a):
    headers, _ = tenant_a
    csv_content = "zone_code,pincode\nUNKNOWN_ZONE_CODE_123,400001\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 422
    assert "does not exist" in resp.text.lower()


@pytest.mark.parametrize(
    "invalid_pincode",
    [
        "12345",
        "1234567",
        "ABCDEF",
        "400.01",
        "400@01",
        "-40001",
        "000000",
    ],
)
def test_upload_serviceability_invalid_pincode_in_row(tenant_a, invalid_pincode):
    headers, _ = tenant_a
    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Row Val Zone", "code": "ROW_VAL_ZONE", "description": "Row val zone", "pincodes": ["400001"]},
        headers=headers,
    )
    assert z_resp.status_code == 201

    csv_content = f"zone_code,pincode\nROW_VAL_ZONE,{invalid_pincode}\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 422


def test_upload_serviceability_duplicate_pincode_different_zone_in_db(tenant_a):
    headers, _ = tenant_a
    r1 = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone Alpha", "code": "ZONE_ALPHA", "description": "Zone Alpha desc", "pincodes": ["400080"]},
        headers=headers,
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone Beta", "code": "ZONE_BETA", "description": "Zone Beta desc", "pincodes": ["400090"]},
        headers=headers,
    )
    assert r2.status_code == 201

    csv_content = "zone_code,pincode\nZONE_BETA,400080\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 409
    assert "already assigned" in resp.text.lower()


def test_upload_serviceability_duplicate_pincode_different_zone_in_file(tenant_a):
    headers, _ = tenant_a
    r1 = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone One InFile", "code": "Z_ONE_FILE", "description": "Zone One desc", "pincodes": ["400015"]},
        headers=headers,
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Zone Two InFile", "code": "Z_TWO_FILE", "description": "Zone Two desc", "pincodes": ["400016"]},
        headers=headers,
    )
    assert r2.status_code == 201

    csv_content = "zone_code,pincode\nZ_ONE_FILE,400085\nZ_TWO_FILE,400085\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 409
    assert "multiple zones" in resp.text.lower()


def test_upload_serviceability_atomic_all_or_nothing(tenant_a):
    headers, _ = tenant_a
    z_resp = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Atomic Zone Test", "code": "ATOMIC_ZONE", "description": "Atomic zone desc", "pincodes": ["400091"]},
        headers=headers,
    )
    assert z_resp.status_code == 201

    csv_content = "zone_code,pincode\nATOMIC_ZONE,400092\nATOMIC_ZONE,BAD_PIN\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers)
    assert resp.status_code == 422

    get_serv = client.get("/api/v1/delivery/serviceability/400092", headers=headers)
    assert get_serv.status_code == 200
    assert get_serv.json()["data"]["is_serviceable"] is False


def test_upload_serviceability_tenant_isolation(tenant_a, tenant_b):
    headers_a, _ = tenant_a
    headers_b, _ = tenant_b

    r = client.post(
        "/api/v1/delivery/zones",
        json={"name": "Tenant A Upload Zone", "code": "T_A_UP_ZONE", "description": "Tenant A upload zone", "pincodes": ["400098"]},
        headers=headers_a,
    )
    assert r.status_code == 201

    csv_content = "zone_code,pincode\nT_A_UP_ZONE,400099\n"
    files = {"file": ("pincodes.csv", csv_content.encode("utf-8"), "text/csv")}
    resp_b = client.post("/api/v1/delivery/serviceability/upload", files=files, headers=headers_b)
    assert resp_b.status_code == 422





