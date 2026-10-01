import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.schemas.gst_rate import GstRateResponse

client = TestClient(app)


def _register_tenant_admin(prefix: str):
    """Helper to register and login a distinct tenant admin."""
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@testcorp.com"
    password = "Password123!"

    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": password,
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    reg_data = reg_resp.json()
    tenant_id = reg_data["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
        "slug": slug,
        "email": email,
    }


@pytest.fixture
def tenant_a():
    return _register_tenant_admin("gst-a")


@pytest.fixture
def tenant_b():
    return _register_tenant_admin("gst-b")


def test_gst_rate_detail_success_same_tenant(tenant_a):
    """Tenant A can successfully retrieve its own GST rate by ID."""
    headers = tenant_a["headers"]
    payload = {
        "hsn_code": "8471",
        "gst_rate": "18.00",
    }
    create_resp = client.post("/api/v1/gst-rates", json=payload, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    rate_id = created["id"]

    # Detail GET
    detail_resp = client.get(f"/api/v1/gst-rates/{rate_id}", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text
    data = detail_resp.json()

    assert data["id"] == rate_id
    assert data["tenant_id"] == tenant_a["tenant_id"]
    assert data["hsn_code"] == "8471"
    assert Decimal(str(data["gst_rate"])) == Decimal("18.00")
    assert Decimal(str(data["cgst"])) == Decimal("9.00")
    assert Decimal(str(data["sgst"])) == Decimal("9.00")
    assert Decimal(str(data["igst"])) == Decimal("18.00")
    assert data["status"] is True
    assert "created_at" in data

    # Verify response schema compatibility
    validated = GstRateResponse.model_validate(data)
    assert validated.id == rate_id


def test_gst_rate_detail_non_existent(tenant_a):
    """Requesting a non-existent GST rate returns 404."""
    headers = tenant_a["headers"]
    resp = client.get("/api/v1/gst-rates/999999", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("message") == "GST rate not found" or body.get("detail") == "GST rate not found" or "not found" in str(body).lower()


def test_gst_rate_detail_cross_tenant_isolation(tenant_a, tenant_b):
    """Tenant B requesting Tenant A's GST rate returns 404 (no leak)."""
    # Create rate in Tenant A
    create_resp = client.post(
        "/api/v1/gst-rates",
        json={"hsn_code": "8504", "gst_rate": "12.00"},
        headers=tenant_a["headers"],
    )
    assert create_resp.status_code == 201, create_resp.text
    rate_a_id = create_resp.json()["id"]

    # Tenant B tries to access Tenant A's GST rate
    cross_resp = client.get(
        f"/api/v1/gst-rates/{rate_a_id}",
        headers=tenant_b["headers"],
    )
    assert cross_resp.status_code == 404
    body = cross_resp.json()
    assert "not found" in str(body).lower()


def test_gst_rate_detail_unauthenticated():
    """Unauthenticated request is rejected with 401."""
    resp = client.get("/api/v1/gst-rates/1")
    assert resp.status_code == 401


def test_gst_rate_detail_insufficient_permissions(tenant_a):
    """User without billing:read permission is rejected with 403."""
    db = SessionLocal()
    try:
        # Create a restricted role in Tenant A without billing:read
        restricted_role = Role(
            tenant_id=tenant_a["tenant_id"],
            name=f"limited-{uuid.uuid4().hex[:6]}",
            permissions=["customers:read"],
        )
        db.add(restricted_role)
        db.commit()
        db.refresh(restricted_role)

        # Create a user with this restricted role
        user_email = f"restricted-{uuid.uuid4().hex[:6]}@testcorp.com"
        restricted_user = User(
            tenant_id=tenant_a["tenant_id"],
            role_id=restricted_role.id,
            email=user_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Restricted User",
            is_active=True,
        )
        db.add(restricted_user)
        db.commit()
    finally:
        db.close()

    # Login as restricted user
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    restricted_headers = {"Authorization": f"Bearer {token}"}

    # Attempt to GET GST rate
    resp = client.get("/api/v1/gst-rates/1", headers=restricted_headers)
    assert resp.status_code == 403
    assert "billing:read" in str(resp.json())
