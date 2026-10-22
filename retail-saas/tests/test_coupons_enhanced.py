import uuid
from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.coupon import Coupon, CouponRedemption
from app.models.customer import Customer
from app.models.store import Store

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
def tenant():
    return create_tenant_client("cpn-enh")


@pytest.fixture
def other_tenant():
    return create_tenant_client("cpn-other-enh")


# ==============================================================================
# 1. BULK GENERATE UNIQUE VOUCHER CODES
# ==============================================================================

def test_bulk_generate_coupons(tenant):
    """Test POST /api/v1/coupons/bulk-generate creates N unique valid coupons."""
    today = date.today()
    future = today + timedelta(days=30)

    payload = {
        "prefix": "DIWALI",
        "count": 5,
        "description": "Diwali Festival 20% Off Voucher",
        "discount_type": "percentage",
        "discount_value": 20.0,
        "minimum_order_amount": 100.0,
        "maximum_discount": 500.0,
        "usage_limit": 1,
        "usage_limit_per_customer": 1,
        "start_date": today.isoformat(),
        "end_date": future.isoformat(),
    }

    resp = client.post(
        "/api/v1/coupons/bulk-generate",
        json=payload,
        headers=tenant["headers"],
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["generated_count"] == 5
    assert len(data["coupons"]) == 5

    codes = [c["code"] for c in data["coupons"]]
    assert len(set(codes)) == 5, "All generated codes must be unique"
    for c in data["coupons"]:
        assert c["code"].startswith("DIWALI")
        assert c["discount_type"] == "percentage"
        assert float(c["discount_value"]) == 20.0
        assert c["is_active"] is True


# ==============================================================================
# 2. EXPORT COUPONS TO EXCEL, CSV, AND PDF
# ==============================================================================

def test_export_coupons_excel_csv_pdf(tenant):
    """Test GET /api/v1/coupons/export produces valid Excel, CSV, and PDF streams."""
    today = date.today()
    future = today + timedelta(days=15)

    # Create at least one coupon
    client.post(
        "/api/v1/coupons",
        json={
            "code": "EXPORT10",
            "description": "Export test coupon",
            "discount_type": "percentage",
            "discount_value": 10.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )

    # 1. Excel export
    resp_excel = client.get(
        "/api/v1/coupons/export?format=excel",
        headers=tenant["headers"],
    )
    assert resp_excel.status_code == 200
    assert "spreadsheetml" in resp_excel.headers["content-type"]
    assert len(resp_excel.content) > 100

    # 2. CSV export
    resp_csv = client.get(
        "/api/v1/coupons/export?format=csv",
        headers=tenant["headers"],
    )
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    csv_text = resp_csv.content.decode("utf-8")
    assert "EXPORT10" in csv_text
    assert "Coupon Code" in csv_text

    # 3. PDF export
    resp_pdf = client.get(
        "/api/v1/coupons/export?format=pdf",
        headers=tenant["headers"],
    )
    assert resp_pdf.status_code == 200
    assert "application/pdf" in resp_pdf.headers["content-type"]
    assert resp_pdf.content.startswith(b"%PDF")

    # 4. Invalid format rejected with 422
    resp_bad = client.get(
        "/api/v1/coupons/export?format=xml",
        headers=tenant["headers"],
    )
    assert resp_bad.status_code == 422


# ==============================================================================
# 3. APPLICABLE COUPONS & CART RECOMMENDATIONS
# ==============================================================================

def test_applicable_coupons_recommendations(tenant):
    """Test GET /api/v1/coupons/applicable categorizes coupons into applicable vs locked with shortfall."""
    today = date.today()
    future = today + timedelta(days=20)

    # Coupon 1: min order 50
    client.post(
        "/api/v1/coupons",
        json={
            "code": "TIER1A",
            "description": "Tier 1 10% Off",
            "discount_type": "percentage",
            "discount_value": 10.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 100,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )

    # Coupon 2: min order 200
    client.post(
        "/api/v1/coupons",
        json={
            "code": "TIER2B",
            "description": "Tier 2 25% Off",
            "discount_type": "percentage",
            "discount_value": 25.0,
            "minimum_order_amount": 200.0,
            "usage_limit": 100,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )

    # Check for cart amount of 100: TIER1A should be applicable, TIER2B should be locked with shortfall 100
    resp = client.get(
        "/api/v1/coupons/applicable?order_amount=100.0",
        headers=tenant["headers"],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["order_amount"] == 100.0

    app_codes = [item["coupon"]["code"] for item in data["applicable_coupons"]]
    assert "TIER1A" in app_codes
    tier1_item = next(i for i in data["applicable_coupons"] if i["coupon"]["code"] == "TIER1A")
    assert tier1_item["is_applicable"] is True
    assert tier1_item["discount_amount"] == 10.0
    assert tier1_item["final_amount"] == 90.0

    locked_codes = [item["coupon"]["code"] for item in data["locked_coupons"]]
    assert "TIER2B" in locked_codes
    tier2_item = next(i for i in data["locked_coupons"] if i["coupon"]["code"] == "TIER2B")
    assert tier2_item["is_applicable"] is False
    assert tier2_item["shortfall"] == 100.0
    assert "100.00" in tier2_item["message"]


# ==============================================================================
# 4. COUPON REDEMPTIONS TRACKING & PER-CUSTOMER USAGE LIMIT
# ==============================================================================

def test_coupon_redemption_and_per_customer_limit(tenant):
    """Test that customer redemptions are recorded and per-customer limit is strictly enforced."""
    today = date.today()
    future = today + timedelta(days=15)

    # Create coupon with usage_limit_per_customer = 1
    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "ONCE10A",
            "description": "One time use per customer",
            "discount_type": "fixed",
            "discount_value": 20.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 100,
            "usage_limit_per_customer": 1,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    coupon_id = create_resp.json()["id"]

    # First validation with customer_id=999 succeeds
    val_resp1 = client.post(
        "/api/v1/coupons/validate",
        json={
            "coupon_code": "ONCE10A",
            "order_amount": 100.0,
            "customer_id": 999,
        },
        headers=tenant["headers"],
    )
    assert val_resp1.status_code == 200
    assert val_resp1.json()["valid"] is True

    # Simulate manual redemption record in DB
    db = SessionLocal()
    redemption = CouponRedemption(
        tenant_id=tenant["tenant_id"],
        coupon_id=coupon_id,
        customer_id=999,
        customer_phone="9876543210",
        discount_amount=Decimal("20.00"),
        order_amount=Decimal("100.00"),
    )
    db.add(redemption)
    cpn = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    cpn.used_count += 1
    db.commit()
    db.close()

    # Second validation for same customer_id=999 fails with 400 (per-customer limit exceeded)
    val_resp2 = client.post(
        "/api/v1/coupons/validate",
        json={
            "coupon_code": "ONCE10A",
            "order_amount": 100.0,
            "customer_id": 999,
        },
        headers=tenant["headers"],
    )
    assert val_resp2.status_code == 400
    assert "usage limit" in val_resp2.json()["message"].lower()

    # Different customer_id=888 can still validate successfully
    val_resp3 = client.post(
        "/api/v1/coupons/validate",
        json={
            "coupon_code": "ONCE10A",
            "order_amount": 100.0,
            "customer_id": 888,
        },
        headers=tenant["headers"],
    )
    assert val_resp3.status_code == 200

    # View redemptions list endpoint
    red_resp = client.get(
        f"/api/v1/coupons/{coupon_id}/redemptions",
        headers=tenant["headers"],
    )
    assert red_resp.status_code == 200
    red_list = red_resp.json()
    assert len(red_list) == 1
    assert red_list[0]["customer_id"] == 999
    assert red_list[0]["discount_amount"] == 20.0


# ==============================================================================
# 5. SOFT-DELETE ON USED COUPON PRESERVES AUDIT INTEGRITY
# ==============================================================================

def test_delete_used_coupon_soft_deletes_safely(tenant):
    """Deleting a coupon with used_count > 0 archives and deactivates it without breaking history."""
    today = date.today()
    future = today + timedelta(days=10)

    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "USED10A",
            "description": "Used coupon for deletion test",
            "discount_type": "fixed",
            "discount_value": 15.0,
            "minimum_order_amount": 50.0,
            "usage_limit": 50,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )
    coupon_id = create_resp.json()["id"]

    # Simulate usage
    db = SessionLocal()
    cpn = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    cpn.used_count = 5
    db.commit()
    db.close()

    # Delete coupon
    del_resp = client.delete(
        f"/api/v1/coupons/{coupon_id}",
        headers=tenant["headers"],
    )
    assert del_resp.status_code == 200
    assert "deactivated and archived" in del_resp.json()["message"]

    # Verify coupon is now hidden from get / list (returns 404)
    get_resp = client.get(
        f"/api/v1/coupons/{coupon_id}",
        headers=tenant["headers"],
    )
    assert get_resp.status_code == 404

    # Verify DB record is preserved as is_deleted=True
    db = SessionLocal()
    db_cpn = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    assert db_cpn is not None
    assert db_cpn.is_deleted is True
    assert db_cpn.is_active is False
    db.close()


# ==============================================================================
# 6. CROSS-TENANT ISOLATION ON NEW ENDPOINTS
# ==============================================================================

def test_new_endpoints_cross_tenant_isolation(tenant, other_tenant):
    """Tenant B cannot access Tenant A's redemptions or exported data."""
    today = date.today()
    future = today + timedelta(days=10)

    create_resp = client.post(
        "/api/v1/coupons",
        json={
            "code": "ISOLATE10",
            "description": "Tenant A exclusive",
            "discount_type": "fixed",
            "discount_value": 10.0,
            "minimum_order_amount": 30.0,
            "usage_limit": 10,
            "start_date": today.isoformat(),
            "end_date": future.isoformat(),
        },
        headers=tenant["headers"],
    )
    cpn_id = create_resp.json()["id"]

    # Tenant B cannot view Tenant A's redemptions
    resp_b = client.get(
        f"/api/v1/coupons/{cpn_id}/redemptions",
        headers=other_tenant["headers"],
    )
    assert resp_b.status_code == 404

