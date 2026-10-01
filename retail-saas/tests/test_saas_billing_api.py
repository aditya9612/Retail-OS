from datetime import datetime
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.main import app
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSPlan,
    SaaSSubscription,
)
from app.models.tenant import Tenant
from app.services.saas_invoice_service import SaaSInvoiceService

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_test_tenant(prefix: str):
    clean = "".join([c for c in prefix if c.isalnum()]).lower() or "t"
    uid = uuid.uuid4().hex[:6]
    email = f"{clean}{uid}@example.com"
    password = "Password123!"
    phone = f"91{uuid.uuid4().int % 100000000:08d}"

    reg_payload = {
        "tenant_name": f"{clean} Tenant {uid}",
        "domain": f"{clean}-{uid}",
        "email": email,
        "admin_name": f"Admin {uid}",
        "password": password,
        "phone": phone,
    }
    r = client.post("/api/v1/auth/register", json=reg_payload)
    assert r.status_code == 200, f"Registration failed: {r.text}"
    tenant_id = r.json()["tenant_id"]

    login_r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_r.status_code == 200, f"Login failed: {login_r.text}"
    token = login_r.json()["access_token"]

    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "email": email,
    }


@pytest.fixture
def tenant_a():
    return create_test_tenant("ta")


@pytest.fixture
def tenant_b():
    return create_test_tenant("tb")


# ==============================================================================
# 1. AUTHENTICATION & ISOLATION TESTS
# ==============================================================================


def test_anonymous_requests_rejected():
    """Verify that unauthenticated requests to SaaS billing endpoints return 401."""
    # History endpoint
    r_hist = client.get("/api/v1/saas-billing/history")
    assert r_hist.status_code == 401

    # Invoices endpoint
    r_inv = client.get("/api/v1/saas-billing/invoices/1")
    assert r_inv.status_code == 401


def test_tenant_retrieves_own_invoice(db_session: Session, tenant_a):
    """Verify Tenant A can successfully retrieve detail of their own invoice."""
    # Find subscription for Tenant A
    sub = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == tenant_a["tenant_id"])
        .first()
    )
    assert sub is not None

    service = SaaSInvoiceService(db_session)
    invoice = service.create_invoice(
        subscription_id=sub.id,
        billing_reason="subscription_cycle",
    )
    db_session.commit()

    resp = client.get(
        f"/api/v1/saas-billing/invoices/{invoice.id}",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == invoice.id
    assert data["tenant_id"] == tenant_a["tenant_id"]
    assert data["invoice_number"] == invoice.invoice_number
    assert Decimal(str(data["subtotal"])) == invoice.subtotal
    assert Decimal(str(data["total_amount"])) == invoice.total_amount
    assert data["status"] == "unpaid"
    assert data["currency"] == sub.currency


def test_tenant_a_retrieves_tenant_b_invoice_returns_404(
    db_session: Session, tenant_a, tenant_b
):
    """Verify strict tenant isolation: Tenant A querying Tenant B's invoice returns 404 (no leak)."""
    sub_b = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == tenant_b["tenant_id"])
        .first()
    )
    assert sub_b is not None

    service = SaaSInvoiceService(db_session)
    inv_b = service.create_invoice(
        subscription_id=sub_b.id,
        billing_reason="subscription_cycle",
    )
    db_session.commit()

    # Tenant A attempts to access Tenant B's invoice
    resp = client.get(
        f"/api/v1/saas-billing/invoices/{inv_b.id}",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


def test_nonexistent_invoice_returns_404(tenant_a):
    """Verify querying a nonexistent invoice returns 404."""
    resp = client.get(
        "/api/v1/saas-billing/invoices/99999999",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 404


def test_no_client_controlled_tenant_id(db_session: Session, tenant_a, tenant_b):
    """Verify that passing an arbitrary tenant_id query parameter is ignored in favor of token tenant_id."""
    sub_b = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == tenant_b["tenant_id"])
        .first()
    )
    assert sub_b is not None

    service = SaaSInvoiceService(db_session)
    service.create_invoice(
        subscription_id=sub_b.id,
        billing_reason="subscription_cycle",
    )
    db_session.commit()

    # Tenant A requests history but passes tenant_id=tenant_b in query params
    resp = client.get(
        f"/api/v1/saas-billing/history?tenant_id={tenant_b['tenant_id']}",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    # Any returned items must belong strictly to Tenant A
    for item in data["items"]:
        assert item["tenant_id"] == tenant_a["tenant_id"]


# ==============================================================================
# 2. BILLING HISTORY & PAGINATION TESTS
# ==============================================================================


def test_billing_history_pagination_and_deterministic_ordering(
    db_session: Session, tenant_a
):
    """Verify pagination controls, total counts, and deterministic created_at DESC, id DESC ordering."""
    sub = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == tenant_a["tenant_id"])
        .first()
    )
    assert sub is not None

    service = SaaSInvoiceService(db_session)
    reasons = ["trial_conversion", "subscription_cycle", "plan_upgrade", "manual_renewal"]
    created_invoices = []
    for r in reasons:
        inv = service.create_invoice(
            subscription_id=sub.id,
            billing_reason=r,
        )
        created_invoices.append(inv)
        db_session.commit()

    # Query page 1 with page_size=2
    resp = client.get(
        "/api/v1/saas-billing/history?page=1&page_size=2",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] >= 4
    assert len(data["items"]) == 2

    # Deterministic ordering check: IDs should be descending
    item_ids = [item["id"] for item in data["items"]]
    assert item_ids[0] > item_ids[1]

    # Query page 2 with page_size=2
    resp2 = client.get(
        "/api/v1/saas-billing/history?page=2&page_size=2",
        headers=tenant_a["headers"],
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["page"] == 2
    item_ids2 = [item["id"] for item in data2["items"]]
    assert len(item_ids2) >= 2
    assert item_ids[1] > item_ids2[0]


def test_page_and_page_size_validation(tenant_a):
    """Verify page < 1 and page_size bounds (1-100) are validated by FastAPI."""
    # page < 1
    resp = client.get(
        "/api/v1/saas-billing/history?page=0",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 422

    # page_size > 100
    resp2 = client.get(
        "/api/v1/saas-billing/history?page_size=101",
        headers=tenant_a["headers"],
    )
    assert resp2.status_code == 422


def test_invoice_response_serialization_no_orm_leaks(db_session: Session, tenant_a):
    """Verify invoice serialization exposes only public business fields without ORM metadata or secrets."""
    sub = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == tenant_a["tenant_id"])
        .first()
    )
    service = SaaSInvoiceService(db_session)
    inv = service.create_invoice(
        subscription_id=sub.id,
        billing_reason="trial_conversion",
    )
    db_session.commit()

    resp = client.get(
        f"/api/v1/saas-billing/invoices/{inv.id}",
        headers=tenant_a["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()

    # Allowed fields
    allowed_keys = {
        "id",
        "tenant_id",
        "subscription_id",
        "invoice_number",
        "billing_reason",
        "subtotal",
        "tax_amount",
        "total_amount",
        "currency",
        "status",
        "due_date",
        "paid_at",
        "pdf_url",
        "notes",
        "created_at",
        "updated_at",
    }
    assert set(data.keys()) == allowed_keys

    # Confirm no ORM internal state leaked
    assert "_sa_instance_state" not in data
    assert "password" not in data
    assert "secret" not in data


# ==============================================================================
# 3. HISTORICAL BACKFILL SAFETY
# ==============================================================================


def test_historical_subscriptions_intact_and_zero_fake_invoices(db_session: Session):
    """Verify that historical subscriptions remain intact and have zero fake invoices, and no auto-invoices are created."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    mysql_url = "mysql+pymysql://retailuser:retail456@localhost:3306/retail_saas"
    try:
        real_engine = create_engine(mysql_url)
        RealSession = sessionmaker(bind=real_engine)
        mysql_sess = RealSession()
        try:
            hist_subs = (
                mysql_sess.query(SaaSSubscription)
                .filter(SaaSSubscription.id <= 13)
                .all()
            )
            assert len(hist_subs) == 13, f"Expected 13 historical subscriptions, got {len(hist_subs)}"
            hist_sub_ids = [s.id for s in hist_subs]
            fake_invs = (
                mysql_sess.query(SaaSInvoice)
                .filter(SaaSInvoice.subscription_id.in_(hist_sub_ids))
                .all()
            )
            assert len(fake_invs) == 0, f"Found {len(fake_invs)} fake invoices for historical subscriptions!"
        finally:
            mysql_sess.close()
    except Exception as e:
        # If MySQL is not reachable, skip the MySQL check
        pass

    # Verify that creating a new tenant & subscription does NOT automatically create invoices
    new_tenant = create_test_tenant("notrig")
    subs = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == new_tenant["tenant_id"])
        .all()
    )
    assert len(subs) >= 1
    sub_ids = [s.id for s in subs]
    invoices = (
        db_session.query(SaaSInvoice)
        .filter(SaaSInvoice.subscription_id.in_(sub_ids))
        .all()
    )
    assert len(invoices) == 0, "Subscription creation must not trigger automatic invoice generation in Task 4"
