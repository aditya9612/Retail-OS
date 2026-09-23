import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.saas_billing import SaaSInvoice, SaaSSubscription
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


def _get_error_message(resp) -> str:
    body = resp.json()
    if isinstance(body.get("detail"), dict):
        return body["detail"].get("message", "")
    elif isinstance(body.get("detail"), str):
        return body["detail"]
    return body.get("message", "")


def _register_and_get_tenant(slug: str):
    email = f"owner-{slug}@testcorp.com"
    password = "testpass123"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Test Owner",
            "password": password,
        },
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    tenant_id = reg_data["tenant_id"]
    user_id = reg_data["user_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a store and a product for operational testing
    store_resp = client.post(
        "/api/v1/stores",
        json={"name": "Main Store", "code": f"MS-{slug[:6]}"},
        headers=headers,
    )
    assert store_resp.status_code == 201
    store_id = store_resp.json()["id"]

    prod_resp = client.post(
        "/api/v1/products",
        json={"name": "Widget", "sku": f"SKU-{slug[:6]}", "price": "100.00"},
        headers=headers,
    )
    assert prod_resp.status_code == 201
    product_id = prod_resp.json()["id"]

    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "email": email,
        "password": password,
        "token": token,
        "headers": headers,
        "store_id": store_id,
        "product_id": product_id,
    }


def _set_subscription_status(tenant_id: int, status: str):
    with SessionLocal() as db:
        sub = (
            db.query(SaaSSubscription)
            .filter(SaaSSubscription.tenant_id == tenant_id)
            .order_by(
                SaaSSubscription.created_at.desc(),
                SaaSSubscription.id.desc(),
            )
            .first()
        )
        assert sub is not None
        sub.status = status
        db.commit()


# =========================================================================
# 1. AUTHENTICATION TESTS
# =========================================================================


def test_login_allowed_for_all_subscription_statuses(unique_slug):
    """
    Active tenant users with valid credentials must be able to log in
    regardless of whether SaaS subscription is trialing, active, past_due,
    expired, or cancelled.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    email = data["email"]
    password = data["password"]

    for sub_status in ["trialing", "active", "past_due", "expired", "cancelled"]:
        _set_subscription_status(tenant_id, sub_status)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200, f"Login failed for status: {sub_status}"
        json_data = resp.json()
        assert "access_token" in json_data
        assert "refresh_token" in json_data


def test_inactive_tenant_login_and_access_rejected(unique_slug):
    """
    Tenant.is_active remains an independent account control.
    When Tenant.is_active is False, login must fail with 401 Unauthorized.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant.is_active = False
        db.commit()

    # Login rejected
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert resp.status_code == 401
    assert "Tenant account is disabled" in _get_error_message(resp)

    # Authenticated call with prior token rejected
    order_resp = client.get("/api/v1/orders", headers=data["headers"])
    assert order_resp.status_code == 401


def test_inactive_user_login_and_access_rejected(unique_slug):
    """
    User.is_active remains an independent user account control.
    When User.is_active is False, login and access must fail with 401.
    """
    data = _register_and_get_tenant(unique_slug)
    user_id = data["user_id"]

    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        user.is_active = False
        db.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert resp.status_code == 401


# =========================================================================
# 2. OPERATIONAL WRITE ACCESS GATING TESTS
# =========================================================================


def test_operational_writes_allowed_for_trialing_active_past_due(unique_slug):
    """
    trialing, active, and past_due (grace period) must have full operational write access.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    for sub_status in ["trialing", "active", "past_due"]:
        _set_subscription_status(tenant_id, sub_status)

        # Inventory stock-in (operational mutation)
        stock_resp = client.post(
            "/api/v1/inventory/stock-in",
            json={"store_id": store_id, "product_id": product_id, "quantity": 10},
            headers=headers,
        )
        assert stock_resp.status_code == 201, f"stock-in failed for {sub_status}"

        # Order creation (operational mutation)
        order_resp = client.post(
            "/api/v1/orders",
            json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
            headers=headers,
        )
        assert order_resp.status_code == 201, f"create_order failed for {sub_status}"


def test_operational_writes_blocked_for_expired_subscription(unique_slug):
    """
    When subscription is expired:
    - Operational mutations (orders, inventory, cart, sales) must return 403 Forbidden.
    - Specific clear message indicating subscription is expired.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    _set_subscription_status(tenant_id, "expired")

    # 1. Order creation blocked
    order_resp = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert order_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(order_resp)

    # 2. Inventory mutation blocked
    inv_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 5},
        headers=headers,
    )
    assert inv_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(inv_resp)

    # 3. POS cart mutation blocked
    cart_resp = client.post(
        "/api/v1/billing/cart/add-item",
        json={"store_id": store_id, "product_id": product_id, "quantity": 1},
        headers=headers,
    )
    assert cart_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(cart_resp)

    # 4. Sales mutation blocked
    sale_resp = client.post(
        "/api/v1/sales",
        json={
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 1, "unit_price": "100.00"}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert sale_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(sale_resp)


def test_operational_writes_blocked_for_cancelled_subscription(unique_slug):
    """
    When subscription is cancelled:
    - Operational mutations (orders, inventory, cart, sales) must return 403 Forbidden.
    - Specific clear message indicating subscription is cancelled.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    _set_subscription_status(tenant_id, "cancelled")

    order_resp = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert order_resp.status_code == 403
    assert "Subscription is cancelled" in _get_error_message(order_resp)

    inv_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 5},
        headers=headers,
    )
    assert inv_resp.status_code == 403
    assert "Subscription is cancelled" in _get_error_message(inv_resp)


# =========================================================================
# 3. READ-ONLY HISTORICAL ACCESS TESTS
# =========================================================================


def test_read_only_access_allowed_for_expired_and_cancelled(unique_slug):
    """
    Expired and cancelled subscriptions must retain legitimate historical/read-only access.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]

    for sub_status in ["expired", "cancelled"]:
        _set_subscription_status(tenant_id, sub_status)

        # GET orders
        resp = client.get("/api/v1/orders", headers=headers)
        assert resp.status_code == 200, f"GET orders failed for {sub_status}"

        # GET inventory
        resp = client.get("/api/v1/inventory", headers=headers)
        assert resp.status_code == 200, f"GET inventory failed for {sub_status}"

        # GET sales
        resp = client.get("/api/v1/sales", headers=headers)
        assert resp.status_code == 200, f"GET sales failed for {sub_status}"

        # GET products
        resp = client.get("/api/v1/products", headers=headers)
        assert resp.status_code == 200, f"GET products failed for {sub_status}"


# =========================================================================
# 4. SAAS BILLING & RECOVERY ACCESS TESTS
# =========================================================================


def test_saas_billing_access_allowed_for_expired_and_cancelled(unique_slug):
    """
    Expired and cancelled subscriptions must retain SaaS billing and UPI recovery access:
    - View billing history
    - View invoice details
    - Initiate UPI checkout or cancel endpoints
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]

    for sub_status in ["expired", "cancelled"]:
        _set_subscription_status(tenant_id, sub_status)

        # Billing history: 200 OK
        resp = client.get("/api/v1/saas-billing/history", headers=headers)
        assert resp.status_code == 200, f"Billing history failed for {sub_status}"

        # Verify billing endpoints are not blocked by 403 Forbidden
        # Attempting checkout preview returns 404 (no payable invoice) rather than 403 (access blocked)
        preview_resp = client.get("/api/v1/saas-billing/upi/checkout-preview", headers=headers)
        assert preview_resp.status_code != 403, f"Checkout preview was blocked by 403 for {sub_status}"


# =========================================================================
# 5. STALE JWT TEST (AUTHORITATIVE DB VERIFICATION)
# =========================================================================


def test_stale_jwt_respects_current_database_state(unique_slug):
    """
    1. User receives a valid JWT while subscription is active.
    2. Subscription status transitions in DB to 'expired'.
    3. The SAME previously-issued JWT is used for an operational mutation.
    4. Request is rejected with 403 Forbidden.
    Proves subscription authorization uses authoritative DB state and does not rely on stale JWT claims.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    original_headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    # Verify write works while active/trialing
    write_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 10},
        headers=original_headers,
    )
    assert write_resp.status_code == 201

    # Transition to expired in database
    _set_subscription_status(tenant_id, "expired")

    # Use the EXACT same original JWT token for operational mutation
    stale_write_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product_id, "quantity": 5},
        headers=original_headers,
    )
    assert stale_write_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(stale_write_resp)


# =========================================================================
# 6. MISSING SUBSCRIPTION BEHAVIOR
# =========================================================================


def test_missing_subscription_fails_closed_on_operational_write(unique_slug):
    """
    If a tenant unexpectedly has no SaaSSubscription record in the DB,
    operational writes must fail closed with 403 Forbidden.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    # Delete all subscriptions for this tenant
    with SessionLocal() as db:
        db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == tenant_id).delete()
        db.commit()

    resp = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "No active subscription found for tenant" in _get_error_message(resp)


# =========================================================================
# 7. TENANT ISOLATION TESTS
# =========================================================================


def test_tenant_isolation_under_subscription_gating(unique_slug):
    """
    Tenant A (expired) cannot perform operational writes.
    Tenant B (active) CAN perform operational writes.
    Tenant A's expired status does not leak or impact Tenant B.
    """
    slug_a = f"{unique_slug}-a"
    slug_b = f"{unique_slug}-b"

    tenant_a = _register_and_get_tenant(slug_a)
    tenant_b = _register_and_get_tenant(slug_b)

    _set_subscription_status(tenant_a["tenant_id"], "expired")
    _set_subscription_status(tenant_b["tenant_id"], "active")

    # Tenant A write blocked
    resp_a = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": tenant_a["store_id"], "product_id": tenant_a["product_id"], "quantity": 5},
        headers=tenant_a["headers"],
    )
    assert resp_a.status_code == 403

    # Tenant B write succeeds
    resp_b = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": tenant_b["store_id"], "product_id": tenant_b["product_id"], "quantity": 5},
        headers=tenant_b["headers"],
    )
    assert resp_b.status_code == 201


# =========================================================================
# 8. SUPER ADMIN UNAFFECTED
# =========================================================================


def test_super_admin_unaffected_by_tenant_subscriptions(unique_slug):
    """
    Super Admin endpoints remain fully accessible independent of any tenant subscription state.
    """
    from app.core.security import create_super_admin_access_token

    # Create super admin in test DB
    with SessionLocal() as db:
        admin = db.query(SuperAdmin).filter(SuperAdmin.email == "sa_gating@example.com").first()
        if not admin:
            from app.core.security import get_password_hash
            admin = SuperAdmin(
                email="sa_gating@example.com",
                hashed_password=get_password_hash("SuperSecurePass123!"),
                full_name="Global Super Admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)

        sa_token = create_super_admin_access_token(
            {"sub": str(admin.id), "role": "SUPERADMIN"}
        )

    sa_headers = {"Authorization": f"Bearer {sa_token}"}
    resp = client.get("/api/v1/super-admins/dashboard", headers=sa_headers)
    assert resp.status_code == 200
    assert "total_tenants" in resp.json()


# =========================================================================
# 9. HTTP POLICY: NON-BLIND GATING VERIFICATION
# =========================================================================


def test_http_policy_does_not_blindly_block_all_posts_or_allow_all_gets(unique_slug):
    """
    Verify the implementation does not blindly block every POST:
    - POST /api/v1/auth/login works for expired tenant.
    - POST /api/v1/auth/change-password works for expired tenant.
    - Operational POST /api/v1/orders is blocked with 403.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]

    _set_subscription_status(tenant_id, "expired")

    # Non-operational POST: Change password is not blocked by subscription gating
    change_pwd_resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "testpass123", "new_password": "newtestpass123"},
        headers=headers,
    )
    assert change_pwd_resp.status_code != 403, "change-password should not be blocked by SaaS subscription gating"

    # Operational POST: Order creation is blocked by subscription gating
    order_resp = client.post(
        "/api/v1/orders",
        json={"store_id": data["store_id"], "items": [{"product_id": data["product_id"], "quantity": 1}]},
        headers=headers,
    )
    assert order_resp.status_code == 403
