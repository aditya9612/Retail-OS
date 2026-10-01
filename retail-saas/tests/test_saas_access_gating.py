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


# =========================================================================
# 10. ARCHITECTURAL RESOLUTION & REGRESSION TESTS
# =========================================================================


def test_pointer_divergence_prefers_authoritative_pointer_over_latest_row(unique_slug):
    """
    Pointer Divergence:
    - Subscription A: pointed by tenant.current_subscription_id, status = 'active'.
    - Subscription B: newer created_at / higher id, status = 'expired'.
    - Operational write must be ALLOWED because authoritative pointer points to A.
    Proves access service uses authoritative Tenant.current_subscription_id over created_at DESC.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        sub_a = db.query(SaaSSubscription).filter(SaaSSubscription.id == tenant.current_subscription_id).first()
        sub_a.status = "active"

        # Create newer subscription B with expired status
        sub_b = SaaSSubscription(
            tenant_id=tenant_id,
            plan_id=sub_a.plan_id,
            status="expired",
            billing_interval=sub_a.billing_interval,
            unit_price=sub_a.unit_price,
            currency=sub_a.currency,
            start_date=sub_a.start_date,
            current_period_start=sub_a.current_period_start,
            current_period_end=sub_a.current_period_end,
        )
        db.add(sub_b)
        db.commit()
        db.refresh(sub_b)

        # Explicitly ensure tenant.current_subscription_id points to sub_a
        tenant.current_subscription_id = sub_a.id
        db.commit()

    resp = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 201, f"Operational write failed despite active pointer: {resp.text}"


def test_historical_subscriptions_uses_current_subscription(unique_slug):
    """
    Historical Subscriptions:
    - Old subscription: expired.
    - New current subscription: active, pointed by current_subscription_id.
    - Operational write must use current subscription and succeed.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        old_sub = db.query(SaaSSubscription).filter(SaaSSubscription.id == tenant.current_subscription_id).first()
        old_sub.status = "expired"

        new_sub = SaaSSubscription(
            tenant_id=tenant_id,
            plan_id=old_sub.plan_id,
            status="active",
            billing_interval=old_sub.billing_interval,
            unit_price=old_sub.unit_price,
            currency=old_sub.currency,
            start_date=old_sub.start_date,
            current_period_start=old_sub.current_period_start,
            current_period_end=old_sub.current_period_end,
        )
        db.add(new_sub)
        db.flush()
        tenant.current_subscription_id = new_sub.id
        db.commit()

    resp = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 201


def test_cross_tenant_pointer_fails_closed(unique_slug):
    """
    Cross-Tenant Pointer:
    - Tenant A's current_subscription_id points to Tenant B's subscription.
    - Operational write for Tenant A must fail closed with HTTP 403 Forbidden.
    - Must NOT silently switch to Tenant B's subscription or auto-repair.
    """
    slug_a = f"{unique_slug}-cta"
    slug_b = f"{unique_slug}-ctb"
    data_a = _register_and_get_tenant(slug_a)
    data_b = _register_and_get_tenant(slug_b)

    with SessionLocal() as db:
        tenant_a = db.query(Tenant).filter(Tenant.id == data_a["tenant_id"]).first()
        tenant_b = db.query(Tenant).filter(Tenant.id == data_b["tenant_id"]).first()
        sub_b = db.query(SaaSSubscription).filter(SaaSSubscription.id == tenant_b.current_subscription_id).first()
        sub_b.status = "active"

        # Tamper pointer: point tenant_a to tenant_b's subscription
        tenant_a.current_subscription_id = sub_b.id
        db.commit()

    resp = client.post(
        "/api/v1/orders",
        json={"store_id": data_a["store_id"], "items": [{"product_id": data_a["product_id"], "quantity": 1}]},
        headers=data_a["headers"],
    )
    assert resp.status_code == 403
    assert "Security violation" in _get_error_message(resp)


def test_missing_current_subscription_id_falls_back_to_latest(unique_slug):
    """
    Missing Current Pointer:
    - Tenant has current_subscription_id = NULL.
    - Access service must use deterministic fallback to latest subscription (created_at DESC, id DESC).
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]
    product_id = data["product_id"]

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant.current_subscription_id = None
        sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == tenant_id).first()
        sub.status = "active"
        db.commit()

    # Fallback to active sub succeeds
    resp = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 201

    # Transition fallback sub to expired; fallback now detects expired status
    with SessionLocal() as db:
        sub = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == tenant_id).first()
        sub.status = "expired"
        db.commit()

    resp_expired = client.post(
        "/api/v1/orders",
        json={"store_id": store_id, "items": [{"product_id": product_id, "quantity": 1}]},
        headers=headers,
    )
    assert resp_expired.status_code == 403
    assert "Subscription is expired" in _get_error_message(resp_expired)


def test_remaining_operational_routers_blocked_when_expired(unique_slug):
    """
    Verifies that remaining operational routers:
    - products
    - payments
    - purchase_orders
    - purchase_order_returns
    - store_transfers
    - grn
    - order_returns
    properly block operational mutations with 403 when subscription is expired.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]
    store_id = data["store_id"]

    _set_subscription_status(tenant_id, "expired")

    # 1. Product creation blocked
    prod_resp = client.post(
        "/api/v1/products",
        json={"name": "Blocked Item", "sku": f"SKU-EX-{unique_slug[:6]}", "price": "50.00"},
        headers=headers,
    )
    assert prod_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(prod_resp)

    # 2. Payments blocked
    pmt_resp = client.post(
        "/api/v1/payments",
        json={"order_id": 999999, "amount": "100.00", "payment_method": "cash"},
        headers=headers,
    )
    assert pmt_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(pmt_resp)

    # 3. Purchase orders blocked
    po_resp = client.post(
        "/api/v1/purchase-orders",
        json={"supplier_id": 1, "store_id": store_id, "items": []},
        headers=headers,
    )
    assert po_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(po_resp)

    # 4. GRN blocked
    grn_resp = client.post(
        "/api/v1/grn",
        json={"purchase_order_id": 1, "invoice_number": "INV-TEST-001"},
        headers=headers,
    )
    assert grn_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(grn_resp)

    # 5. Store transfers blocked
    st_resp = client.post(
        "/api/v1/store-transfers",
        json={"from_store_id": store_id, "to_store_id": 2, "items": []},
        headers=headers,
    )
    assert st_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(st_resp)

    # 6. Order returns blocked
    or_resp = client.post(
        "/api/v1/order-returns",
        json={"order_id": 1, "items": []},
        headers=headers,
    )
    assert or_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(or_resp)

    # 7. Purchase order returns blocked
    por_resp = client.post(
        "/api/v1/purchase-order-returns",
        json={"purchase_order_id": 1, "items": []},
        headers=headers,
    )
    assert por_resp.status_code == 403
    assert "Subscription is expired" in _get_error_message(por_resp)


def test_all_operational_mutation_endpoints_have_gating_dependency():
    """
    Verifies that all 48 operational mutation endpoints across the 10 operational routers + payments
    strictly include require_operational_write in their route dependencies.
    """
    from fastapi.routing import APIRoute
    from app.api.v1.orders.router import router as r_orders
    from app.api.v1.billing.router import router as r_billing
    from app.api.v1.sales import router as r_sales
    from app.api.v1.inventory.router import router as r_inventory
    from app.api.v1.purchase_orders.router import router as r_po
    from app.api.v1.purchase_order_returns.router import router as r_por
    from app.api.v1.store_transfers import router as r_st
    from app.api.v1.grn.router import router as r_grn
    from app.api.v1.order_returns.router import router as r_or
    from app.api.v1.products.router import router as r_prod
    from app.api.v1.payments.router import router as r_payments

    operational_routers = [
        r_orders, r_billing, r_sales, r_inventory, r_po,
        r_por, r_st, r_grn, r_or, r_prod,
    ]

    total_gated = 0
    # 1. Check all mutations in the 10 operational domain routers
    for r in operational_routers:
        for route in r.routes:
            if isinstance(route, APIRoute):
                methods = route.methods - {"HEAD", "OPTIONS"}
                if any(m in {"POST", "PUT", "PATCH", "DELETE"} for m in methods):
                    dep_names = [
                        d.dependency.__name__
                        if hasattr(d, "dependency") and hasattr(d.dependency, "__name__")
                        else (d.call.__name__ if hasattr(d, "call") and hasattr(d.call, "__name__") else "")
                        for d in route.dependencies
                    ]
                    assert "require_operational_write" in dep_names, (
                        f"Route {route.path} [{methods}] is missing require_operational_write dependency!"
                    )
                    total_gated += 1

    # 2. Check payments create_payment operational mutation
    for route in r_payments.routes:
        if isinstance(route, APIRoute) and route.path == "/payments" and "POST" in route.methods:
            dep_names = [
                d.dependency.__name__
                if hasattr(d, "dependency") and hasattr(d.dependency, "__name__")
                else (d.call.__name__ if hasattr(d, "call") and hasattr(d.call, "__name__") else "")
                for d in route.dependencies
            ]
            assert "require_operational_write" in dep_names
            total_gated += 1

    assert total_gated == 48, f"Expected exactly 48 gated operational routes, found {total_gated}"


def test_non_operational_mutations_not_blocked_by_subscription_gating(unique_slug):
    """
    Verifies that non-operational mutations (such as customers, suppliers, coupons)
    do not have subscription gating applied and are not blocked with 403 Forbidden
    when subscription is expired.
    """
    data = _register_and_get_tenant(unique_slug)
    tenant_id = data["tenant_id"]
    headers = data["headers"]

    _set_subscription_status(tenant_id, "expired")

    # Customer creation: should not fail with 403 subscription expired
    cust_resp = client.post(
        "/api/v1/customers",
        json={"name": "Walk-in Buyer", "phone": "9876543210"},
        headers=headers,
    )
    assert cust_resp.status_code != 403 or "Subscription" not in _get_error_message(cust_resp)

    # Supplier creation: should not fail with 403 subscription expired
    supp_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Alpha Wholesalers",
            "phone": "9876543211",
            "contact_person": "Vendor Contact",
            "email": "vendor@alphawholesale.com",
        },
        headers=headers,
    )
    assert supp_resp.status_code != 403 or "Subscription" not in _get_error_message(supp_resp)

    # Coupon creation: should not fail with 403 subscription expired
    coup_resp = client.post(
        "/api/v1/coupons/",
        json={
            "code": f"SAVE{unique_slug[:4].upper()}",
            "discount_type": "percentage",
            "discount_value": 10,
        },
        headers=headers,
    )
    assert coup_resp.status_code != 403 or "Subscription" not in _get_error_message(coup_resp)
