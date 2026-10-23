import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.delivery_method import DeliveryMethod
from app.models.delivery_partner import DeliveryPartner
from app.models.delivery_zone import DeliveryZone
from app.models.order import Order, OrderTracking
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def create_tenant_session(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"user-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Admin",
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

    # Create default Store
    store = Store(
        tenant_id=tenant_id,
        name=f"Store-{uuid.uuid4().hex[:4]}",
        address="100 Main Market Street",
        is_active=True,
        is_main=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)

    # Create Customer
    customer = Customer(
        tenant_id=tenant_id,
        name="Sunil Patil",
        phone="9876543210",
        email=f"sunil-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Create Delivery Partner
    partner = DeliveryPartner(
        tenant_id=tenant_id,
        name="Express Logistics India",
        code=f"EXP_{uuid.uuid4().hex[:4].upper()}",
        tracking_url_template="https://track.expresslogistics.in/?awb={tracking_number}",
        is_active=True,
    )
    db.add(partner)

    # Create Delivery Method
    method = DeliveryMethod(
        tenant_id=tenant_id,
        name="Same Day Hyperlocal",
        code=f"SAME_DAY_{uuid.uuid4().hex[:4].upper()}",
        cost=Decimal("79.00"),
        estimated_days=0,
        is_active=True,
    )
    db.add(method)

    # Create Delivery Zone
    zone = DeliveryZone(
        tenant_id=tenant_id,
        name="South Mumbai Zone",
        code=f"Z_MUM_{uuid.uuid4().hex[:4].upper()}",
        city="Mumbai",
        state="Maharashtra",
        pincodes=["400001", "400005", "400020"],
        is_active=True,
    )
    db.add(zone)

    db.commit()
    db.refresh(partner)
    db.refresh(method)
    db.refresh(zone)

    data = {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store.id,
        "customer_id": customer.id,
        "partner_id": partner.id,
        "method_id": method.id,
        "zone_id": zone.id,
    }
    db.close()
    return data


def create_test_order(tenant_data, order_number=None, total_amount=Decimal("1500.00"), is_cod=True):
    db = SessionLocal()
    order_num = order_number or f"ORD-{uuid.uuid4().hex[:8].upper()}"
    order = Order(
        tenant_id=tenant_data["tenant_id"],
        store_id=tenant_data["store_id"],
        customer_id=tenant_data["customer_id"],
        order_number=order_num,
        status="confirmed",
        total_amount=total_amount,
        payment_status="pending" if is_cod else "paid",
        delivery_address="Flat 402, Sea View Apartments, Colaba, Mumbai 400005",
        delivery_pincode="400005",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    order_id = order.id
    db.close()
    return order_id, order_num


@pytest.fixture
def t_session_a():
    return create_tenant_session("ent-a")


@pytest.fixture
def t_session_b():
    return create_tenant_session("ent-b")


# ============================================================================
# 1. POST /api/v1/delivery with Partner, Method, Zone, and COD
# ============================================================================

def test_create_delivery_with_partner_and_cod(t_session_a):
    headers = t_session_a["headers"]
    order_id, _ = create_test_order(t_session_a, total_amount=Decimal("2450.00"), is_cod=True)

    payload = {
        "order_id": order_id,
        "partner_id": t_session_a["partner_id"],
        "delivery_method_id": t_session_a["method_id"],
        "zone_id": t_session_a["zone_id"],
        "tracking_number": "AWB-MUM-889900",
        "is_cod": True,
        "cod_amount": 2450.00,
        "delivery_slot": "10:00 AM - 01:00 PM",
    }
    resp = client.post("/api/v1/delivery", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]

    assert data["order_id"] == order_id
    assert data["partner_id"] == t_session_a["partner_id"]
    assert data["partner_name"] == "Express Logistics India"
    assert data["delivery_method_id"] == t_session_a["method_id"]
    assert data["method_name"] == "Same Day Hyperlocal"
    assert data["zone_id"] == t_session_a["zone_id"]
    assert data["is_cod"] is True
    assert Decimal(str(data["cod_amount"])) == Decimal("2450.00")
    assert data["cod_collected"] is False
    assert data["delivery_slot"] == "10:00 AM - 01:00 PM"
    assert data["tracking_number"] == "AWB-MUM-889900"
    assert data["tracking_url"] == "https://track.expresslogistics.in/?awb=AWB-MUM-889900"
    assert data["recipient_name"] == "Sunil Patil"
    assert data["recipient_phone"] == "9876543210"
    assert "Colaba" in data["delivery_address"]
    assert len(data["delivery_otp"]) == 6


# ============================================================================
# 2. GET /api/v1/delivery Pagination, Filters, and Search
# ============================================================================

def test_list_deliveries_pagination_and_filters(t_session_a):
    headers = t_session_a["headers"]

    # Create 3 deliveries with different characteristics
    o1, _ = create_test_order(t_session_a, is_cod=True)
    o2, _ = create_test_order(t_session_a, is_cod=False)
    o3, _ = create_test_order(t_session_a, is_cod=True)

    client.post("/api/v1/delivery", json={"order_id": o1, "delivery_person": "Rider Rajesh", "tracking_number": "TRK-PAG-001", "is_cod": True, "cod_amount": 500}, headers=headers)
    client.post("/api/v1/delivery", json={"order_id": o2, "delivery_person": "Rider Mahesh", "tracking_number": "TRK-PAG-002", "is_cod": False}, headers=headers)
    client.post("/api/v1/delivery", json={"order_id": o3, "delivery_person": "Rider Rajesh", "tracking_number": "TRK-PAG-003", "is_cod": True, "cod_amount": 900}, headers=headers)

    # 1. Test Pagination (page=1, page_size=2)
    resp = client.get("/api/v1/delivery?page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    res = resp.json()
    assert res["success"] is True
    assert len(res["data"]) == 2
    assert res["total"] >= 3
    assert res["page"] == 1
    assert res["page_size"] == 2
    assert res["total_pages"] >= 2

    # 2. Test Filter by delivery_person
    resp_rider = client.get("/api/v1/delivery?delivery_person=Rajesh", headers=headers)
    assert resp_rider.status_code == 200
    items = resp_rider.json()["data"]
    assert len(items) == 2
    assert all("Rajesh" in item["delivery_person"] for item in items)

    # 3. Test Filter by is_cod=true
    resp_cod = client.get("/api/v1/delivery?is_cod=true", headers=headers)
    assert resp_cod.status_code == 200
    cod_items = resp_cod.json()["data"]
    assert len(cod_items) >= 2
    assert all(item["is_cod"] is True for item in cod_items)

    # 4. Test Search by Tracking Number
    resp_search = client.get("/api/v1/delivery?search=TRK-PAG-002", headers=headers)
    assert resp_search.status_code == 200
    search_items = resp_search.json()["data"]
    assert len(search_items) == 1
    assert search_items[0]["tracking_number"] == "TRK-PAG-002"


# ============================================================================
# 3. PATCH /api/v1/delivery/{id}/partner FK Linking
# ============================================================================

def test_assign_partner_with_partner_id_fk(t_session_a):
    headers = t_session_a["headers"]
    partner_id = t_session_a["partner_id"]
    order_id, _ = create_test_order(t_session_a)

    create_resp = client.post("/api/v1/delivery", json={"order_id": order_id}, headers=headers)
    delivery_id = create_resp.json()["data"]["id"]

    patch_resp = client.patch(
        f"/api/v1/delivery/{delivery_id}/partner",
        json={"partner_id": partner_id, "tracking_number": "EXP-AIR-999"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()["data"]
    assert data["partner_id"] == partner_id
    assert data["partner_name"] == "Express Logistics India"
    assert data["tracking_number"] == "EXP-AIR-999"
    assert data["status"] == "assigned"


# ============================================================================
# 4. GET /api/v1/delivery/{id}/label/thermal (Thermal Shipping Label)
# ============================================================================

def test_thermal_delivery_label_html_and_json(t_session_a):
    headers = t_session_a["headers"]
    order_id, order_num = create_test_order(t_session_a, total_amount=Decimal("1200.00"), is_cod=True)

    del_resp = client.post(
        "/api/v1/delivery",
        json={
            "order_id": order_id,
            "delivery_person": "Rider Ramesh",
            "tracking_number": "AWB-THM-123456",
            "is_cod": True,
            "cod_amount": 1200.00,
        },
        headers=headers,
    )
    delivery_id = del_resp.json()["data"]["id"]

    # 1. Mode PREVIEW / Default (Visual Graphic image rendered directly in Swagger UI)
    prev_resp = client.get(f"/api/v1/delivery/{delivery_id}/label/thermal", headers=headers)
    assert prev_resp.status_code == 200
    assert prev_resp.headers["content-type"] == "image/png"
    assert len(prev_resp.content) > 1000

    # 2. Mode explicit 'preview'
    prev_explicit = client.get(f"/api/v1/delivery/{delivery_id}/label/thermal?mode=preview", headers=headers)
    assert prev_explicit.status_code == 200
    assert prev_explicit.headers["content-type"] == "image/png"
    assert len(prev_explicit.content) > 1000

    # 3. Mode 'view' (Browser tab HTML with print preview)
    view_resp = client.get(f"/api/v1/delivery/{delivery_id}/label/thermal?mode=view", headers=headers)
    assert view_resp.status_code == 200
    assert "text/html" in view_resp.headers["content-type"]
    assert view_resp.headers.get("content-disposition") == "inline"
    assert "AWB-THM-123456" in view_resp.text
    assert order_num in view_resp.text
    assert "Sunil Patil" in view_resp.text
    assert "COD: ₹1200.00" in view_resp.text
    assert "4in 6in" in view_resp.text

    # 4. Mode 'download' (HTML attachment file)
    dl_resp = client.get(f"/api/v1/delivery/{delivery_id}/label/thermal?mode=download", headers=headers)
    assert dl_resp.status_code == 200
    assert "text/html" in dl_resp.headers["content-type"]
    assert f'attachment; filename="shipping_label_{order_num}.html"' in dl_resp.headers.get("content-disposition", "")
    assert "AWB-THM-123456" in dl_resp.text

    # 5. Mode 'html' (Direct print compatibility)
    compat_resp = client.get(f"/api/v1/delivery/{delivery_id}/label/thermal?mode=html", headers=headers)
    assert compat_resp.status_code == 200
    assert "text/html" in compat_resp.headers["content-type"]
    assert compat_resp.headers.get("content-disposition") == "inline"

    # 6. Mode JSON
    json_resp = client.get(f"/api/v1/delivery/{delivery_id}/label/thermal?mode=json", headers=headers)
    assert json_resp.status_code == 200
    json_data = json_resp.json()
    assert json_data["success"] is True
    assert json_data["delivery_id"] == delivery_id
    assert json_data["order_number"] == order_num
    assert "html" in json_data


# ============================================================================
# 5. POST /api/v1/delivery/{id}/failed-attempt (NDR - Non Delivery Report)
# ============================================================================

def test_record_failed_delivery_attempt_and_reschedule(t_session_a):
    headers = t_session_a["headers"]
    order_id, _ = create_test_order(t_session_a)

    del_resp = client.post("/api/v1/delivery", json={"order_id": order_id, "delivery_person": "Rider Ramesh"}, headers=headers)
    delivery_id = del_resp.json()["data"]["id"]

    # 1. First Failed Attempt
    attempt_1 = client.post(
        f"/api/v1/delivery/{delivery_id}/failed-attempt",
        json={
            "reason": "Customer premises locked / Door bell unanswered",
            "remarks": "Called 3 times, phone was ringing",
        },
        headers=headers,
    )
    assert attempt_1.status_code == 200
    d1 = attempt_1.json()["data"]
    assert d1["attempt_count"] == 1
    assert "locked" in d1["failure_reason"]

    # 2. Second Failed Attempt with Reschedule Date
    resched_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
    attempt_2 = client.post(
        f"/api/v1/delivery/{delivery_id}/failed-attempt",
        json={
            "reason": "Customer requested delivery tomorrow morning",
            "remarks": "Available between 10am-12pm",
            "reschedule_date": resched_time,
        },
        headers=headers,
    )
    assert attempt_2.status_code == 200
    d2 = attempt_2.json()["data"]
    assert d2["attempt_count"] == 2
    assert d2["estimated_delivery_time"] is not None

    # Verify OrderTracking event in DB
    db = SessionLocal()
    trackings = db.query(OrderTracking).filter(OrderTracking.order_id == order_id).all()
    assert any("Delivery attempt #1 failed" in t.remarks for t in trackings)
    assert any("Delivery attempt #2 failed" in t.remarks for t in trackings)
    db.close()

    # 3. Delivered shipment cannot record failed attempt
    client.patch(f"/api/v1/delivery/{delivery_id}/status", json={"status": "delivered"}, headers=headers)
    blocked = client.post(
        f"/api/v1/delivery/{delivery_id}/failed-attempt",
        json={"reason": "Customer rejected"},
        headers=headers,
    )
    assert blocked.status_code == 409


# ============================================================================
# 6. GET /api/v1/delivery/cod-reconciliation & PATCH /collect-cod
# ============================================================================

def test_cod_reconciliation_and_cash_collection(t_session_a):
    headers = t_session_a["headers"]

    o1, num1 = create_test_order(t_session_a, total_amount=Decimal("1500.00"), is_cod=True)
    o2, num2 = create_test_order(t_session_a, total_amount=Decimal("800.00"), is_cod=True)

    d1 = client.post("/api/v1/delivery", json={"order_id": o1, "delivery_person": "Sanjay Rider", "is_cod": True, "cod_amount": 1500.00}, headers=headers).json()["data"]["id"]
    d2 = client.post("/api/v1/delivery", json={"order_id": o2, "delivery_person": "Sanjay Rider", "is_cod": True, "cod_amount": 800.00}, headers=headers).json()["data"]["id"]

    # Collect COD on d1
    coll_resp = client.patch(f"/api/v1/delivery/{d1}/collect-cod", json={"amount": 1500.00}, headers=headers)
    assert coll_resp.status_code == 200
    assert coll_resp.json()["data"]["cod_collected"] is True

    # Attempt double collection must return 409 Conflict
    coll_double = client.patch(f"/api/v1/delivery/{d1}/collect-cod", json={"amount": 1500.00}, headers=headers)
    assert coll_double.status_code == 409

    # Query COD Reconciliation
    rec_resp = client.get("/api/v1/delivery/cod-reconciliation?delivery_person=Sanjay", headers=headers)
    assert rec_resp.status_code == 200
    rec = rec_resp.json()
    assert rec["success"] is True

    summary = rec["summary"]
    assert summary["total_cod_orders"] == 2
    assert Decimal(str(summary["total_cod_amount"])) == Decimal("2300.00")
    assert summary["collected_orders_count"] == 1
    assert Decimal(str(summary["total_collected_amount"])) == Decimal("1500.00")
    assert summary["pending_orders_count"] == 1
    assert Decimal(str(summary["total_pending_amount"])) == Decimal("800.00")
    assert "Sanjay Rider" in summary["by_delivery_person"]

    deliveries = rec["deliveries"]
    assert len(deliveries) == 2


# ============================================================================
# 7. Cross-Tenant Security Isolation on New Endpoints
# ============================================================================

def test_new_endpoints_cross_tenant_isolation(t_session_a, t_session_b):
    headers_a = t_session_a["headers"]
    headers_b = t_session_b["headers"]

    o_a, _ = create_test_order(t_session_a, is_cod=True)
    d_a = client.post("/api/v1/delivery", json={"order_id": o_a, "delivery_person": "Secret Carrier"}, headers=headers_a).json()["data"]["id"]

    # 1. Tenant B cannot access Tenant A's thermal label
    thm_b = client.get(f"/api/v1/delivery/{d_a}/label/thermal", headers=headers_b)
    assert thm_b.status_code == 404

    # 2. Tenant B cannot post failed attempt to Tenant A's delivery
    fail_b = client.post(f"/api/v1/delivery/{d_a}/failed-attempt", json={"reason": "Door locked"}, headers=headers_b)
    assert fail_b.status_code == 404

    # 3. Tenant B cannot collect COD for Tenant A's delivery
    cod_b = client.patch(f"/api/v1/delivery/{d_a}/collect-cod", json={}, headers=headers_b)
    assert cod_b.status_code == 404

    # 4. Tenant B's COD reconciliation does NOT show Tenant A's deliveries
    rec_b = client.get("/api/v1/delivery/cod-reconciliation", headers=headers_b).json()
    assert not any(d["delivery_id"] == d_a for d in rec_b["deliveries"])



def test_legacy_deliveries_with_null_cod_columns_retrieve_successfully(t_session_a):
    headers = t_session_a["headers"]
    tenant_id = t_session_a["tenant_id"]

    db = SessionLocal()
    order_id, _ = create_test_order(t_session_a)

    # Insert raw delivery row where new columns are explicitly NULL (mimicking old legacy database rows)
    legacy_del = Delivery(
        tenant_id=tenant_id,
        order_id=order_id,
        status="pending",
        delivery_person="Legacy Courier",
        tracking_number=f"TRK-LEGACY-{uuid.uuid4().hex[:6]}",
    )
    # Set explicit None
    legacy_del.is_cod = None
    legacy_del.cod_amount = None
    legacy_del.cod_collected = None
    legacy_del.attempt_count = None
    db.add(legacy_del)
    db.commit()
    db.refresh(legacy_del)
    del_id = legacy_del.id
    db.close()

    # Query GET /api/v1/delivery (must return 200 OK without 422 validation error)
    resp = client.get("/api/v1/delivery", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    matched = [d for d in data if d["id"] == del_id]
    assert len(matched) == 1
    item = matched[0]
    assert item["is_cod"] is False
    assert Decimal(str(item["cod_amount"])) == Decimal("0.00")
    assert item["cod_collected"] is False
    assert item["attempt_count"] == 0
