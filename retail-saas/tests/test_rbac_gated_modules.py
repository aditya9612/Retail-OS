import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.role import Role
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def rbac_setup(unique_slug):
    """Sets up a tenant with an Admin/Owner and an Unprivileged user (no permissions)."""
    # 1. Register tenant (Creates Owner/Admin user)
    owner_email = f"owner-{unique_slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"RBAC Tenant {unique_slug}",
            "slug": unique_slug,
            "email": owner_email,
            "admin_name": "Tenant Owner",
            "password": "Password123!",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    tenant_id = reg.json()["tenant_id"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": "Password123!"},
    )
    owner_token = login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Create store
    store = client.post(
        "/api/v1/stores",
        json={"name": "RBAC Main Store", "code": f"RST-{unique_slug[:6].upper()}"},
        headers=owner_headers,
    ).json()

    # 3. Create restricted role with zero permissions
    db = SessionLocal()
    try:
        restricted_role = Role(
            tenant_id=tenant_id,
            name=f"restricted_{unique_slug}",
            permissions=[],
            is_system=False,
        )
        db.add(restricted_role)
        db.commit()
        db.refresh(restricted_role)

        # 4. Create an unprivileged user
        unpriv_email = f"unprivileged-{unique_slug}@example.com"
        from app.core.security import get_password_hash
        unpriv_user = User(
            tenant_id=tenant_id,
            store_id=store["id"],
            role_id=restricted_role.id,
            email=unpriv_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Unprivileged Staff",
            is_active=True,
            is_deleted=False,
        )
        db.add(unpriv_user)
        db.commit()
    finally:
        db.close()

    # Login as unprivileged user
    unpriv_login = client.post(
        "/api/v1/auth/login",
        json={"email": unpriv_email, "password": "Password123!"},
    )
    assert unpriv_login.status_code == 200, unpriv_login.text
    unpriv_token = unpriv_login.json()["access_token"]
    unpriv_headers = {"Authorization": f"Bearer {unpriv_token}"}

    return {
        "tenant_id": tenant_id,
        "store": store,
        "owner_headers": owner_headers,
        "unpriv_headers": unpriv_headers,
    }


# ==============================================================================
# 1. PAYMENTS RBAC TESTS
# ==============================================================================

def test_payments_rbac_enforcement(rbac_setup):
    owner_headers = rbac_setup["owner_headers"]
    unpriv_headers = rbac_setup["unpriv_headers"]

    # Owner/Admin allowed to list payments (has permissions)
    owner_res = client.get("/api/v1/payments", headers=owner_headers)
    assert owner_res.status_code in (200, 404)

    # Unprivileged user BLOCKED with 403 Forbidden
    unpriv_res = client.get("/api/v1/payments", headers=unpriv_headers)
    assert unpriv_res.status_code == 403
    assert "Missing permission" in unpriv_res.text

    # Payment gateways: Owner allowed, unprivileged blocked
    gw_unpriv = client.get("/api/v1/payments/payment-gateways", headers=unpriv_headers)
    assert gw_unpriv.status_code == 403

    # Webhook logs: Owner allowed, unprivileged blocked
    wh_unpriv = client.get("/api/v1/payments/webhooks", headers=unpriv_headers)
    assert wh_unpriv.status_code == 403


# ==============================================================================
# 2. ORDER RETURNS RBAC TESTS
# ==============================================================================

def test_order_returns_rbac_enforcement(rbac_setup):
    owner_headers = rbac_setup["owner_headers"]
    unpriv_headers = rbac_setup["unpriv_headers"]

    # Owner allowed to list returns
    owner_res = client.get("/api/v1/order-returns", headers=owner_headers)
    assert owner_res.status_code == 200

    # Unprivileged user BLOCKED with 403 Forbidden
    unpriv_res = client.get("/api/v1/order-returns", headers=unpriv_headers)
    assert unpriv_res.status_code == 403
    assert "Missing permission" in unpriv_res.text

    # Order returns stats: Unprivileged blocked
    stats_unpriv = client.get("/api/v1/order-returns/stats", headers=unpriv_headers)
    assert stats_unpriv.status_code == 403


# ==============================================================================
# 3. STORE TRANSFERS RBAC TESTS
# ==============================================================================

def test_store_transfers_rbac_enforcement(rbac_setup):
    owner_headers = rbac_setup["owner_headers"]
    unpriv_headers = rbac_setup["unpriv_headers"]

    # Owner allowed to list store transfers
    owner_res = client.get("/api/v1/store-transfers", headers=owner_headers)
    assert owner_res.status_code == 200

    # Unprivileged user BLOCKED with 403 Forbidden
    unpriv_res = client.get("/api/v1/store-transfers", headers=unpriv_headers)
    assert unpriv_res.status_code == 403
    assert "Missing permission" in unpriv_res.text

    # Store transfer summary: Unprivileged blocked
    sum_unpriv = client.get("/api/v1/store-transfers/summary", headers=unpriv_headers)
    assert sum_unpriv.status_code == 403


# ==============================================================================
# 4. SAAS BILLING & USAGE ROLE RESTRICTION TESTS
# ==============================================================================

def test_saas_billing_and_usage_role_enforcement(rbac_setup):
    owner_headers = rbac_setup["owner_headers"]
    unpriv_headers = rbac_setup["unpriv_headers"]

    # Owner allowed to access SaaS billing history and plans
    plans_owner = client.get("/api/v1/saas-billing/plans", headers=owner_headers)
    assert plans_owner.status_code == 200

    hist_owner = client.get("/api/v1/saas-billing/history", headers=owner_headers)
    assert hist_owner.status_code == 200

    # Unprivileged staff user BLOCKED from SaaS Billing
    plans_unpriv = client.get("/api/v1/saas-billing/plans", headers=unpriv_headers)
    assert plans_unpriv.status_code == 403
    assert "Insufficient role" in plans_unpriv.text

    cancel_unpriv = client.post("/api/v1/saas-billing/subscription/cancel", headers=unpriv_headers)
    assert cancel_unpriv.status_code == 403

    # SaaS Usage: Owner allowed, Unprivileged staff blocked
    usage_unpriv = client.get("/api/v1/saas/usage", headers=unpriv_headers)
    assert usage_unpriv.status_code == 403

