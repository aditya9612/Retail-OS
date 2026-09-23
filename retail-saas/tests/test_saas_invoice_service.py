from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSInvoiceSequence,
    SaaSPlan,
    SaaSSubscription,
)
from app.models.sale import Sale
from app.models.tenant import Tenant
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.saas_invoice_service import (
    ALLOWED_BILLING_REASONS,
    SaaSInvoiceService,
)
from app.services.saas_subscription_service import SaaSSubscriptionService


from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_tenant_and_sub(db_session: Session):
    """Creates an isolated tenant and subscription for testing SaaS invoice creation."""
    uid = uuid.uuid4().hex[:6]
    email = f"saas_inv_{uid}@example.com"
    phone = f"91{uuid.uuid4().int % 100000000:08d}"

    reg_payload = {
        "tenant_name": f"Invoice Test Tenant {uid}",
        "domain": f"inv-{uid}",
        "email": email,
        "admin_name": f"Admin {uid}",
        "password": "Password123!",
        "phone": phone,
    }
    resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert resp.status_code == 200, resp.text
    tenant_id = resp.json()["tenant_id"]

    subscription = (
        db_session.query(SaaSSubscription)
        .filter(SaaSSubscription.tenant_id == tenant_id)
        .order_by(SaaSSubscription.id.desc())
        .first()
    )
    assert subscription is not None

    return {
        "tenant_id": tenant_id,
        "subscription_id": subscription.id,
        "unit_price": subscription.unit_price,
        "currency": subscription.currency,
    }


# ==============================================================================
# 1. INVOICE CREATION & SNAPSHOT PRICING TESTS
# ==============================================================================


def test_valid_invoice_creation(db_session: Session, sample_tenant_and_sub):
    """Verify successful invoice creation from an authoritative subscription."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    service = SaaSInvoiceService(db_session)

    invoice = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="subscription_cycle",
        notes="Monthly subscription cycle invoice",
    )
    db_session.commit()

    assert invoice.id is not None
    assert invoice.subscription_id == sub_id
    assert invoice.tenant_id == sample_tenant_and_sub["tenant_id"]
    assert invoice.subtotal == sample_tenant_and_sub["unit_price"]
    assert invoice.tax_amount == Decimal("0.00")
    assert invoice.total_amount == sample_tenant_and_sub["unit_price"]
    assert invoice.currency == sample_tenant_and_sub["currency"]
    assert invoice.status == "unpaid"
    assert invoice.paid_at is None
    assert invoice.pdf_url is None
    assert invoice.notes == "Monthly subscription cycle invoice"
    assert invoice.invoice_number.startswith("INV-SAAS-")


def test_subscription_not_found(db_session: Session):
    """Verify 404 NotFoundException when subscription_id does not exist."""
    service = SaaSInvoiceService(db_session)
    with pytest.raises(NotFoundException):
        service.create_invoice(subscription_id=99999999)


def test_plan_price_change_does_not_change_invoice_amount(
    db_session: Session, sample_tenant_and_sub
):
    """Verify that invoice subtotal comes strictly from subscription snapshot, NOT modified plan price."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    subscription = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).one()

    # Modify plan catalog price directly
    plan = db_session.query(SaaSPlan).filter(SaaSPlan.id == subscription.plan_id).one()
    original_plan_price = plan.price
    plan.price = Decimal("9999.00")
    db_session.flush()

    try:
        service = SaaSInvoiceService(db_session)
        invoice = service.create_invoice(
            subscription_id=sub_id,
            billing_reason="subscription_cycle",
        )
        db_session.commit()

        # Invoice subtotal must match subscription.unit_price, NOT plan.price
        assert invoice.subtotal == subscription.unit_price
        assert invoice.subtotal != plan.price
        assert invoice.total_amount == subscription.unit_price
    finally:
        # Restore plan price
        plan.price = original_plan_price
        db_session.commit()


def test_correct_currency_snapshot(db_session: Session, sample_tenant_and_sub):
    """Verify invoice currency derives from subscription snapshot."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    subscription = db_session.query(SaaSSubscription).filter(SaaSSubscription.id == sub_id).one()

    service = SaaSInvoiceService(db_session)
    invoice = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="manual_renewal",
    )
    db_session.commit()

    assert invoice.currency == subscription.currency


def test_decimal_precision_and_zero_tax(db_session: Session, sample_tenant_and_sub):
    """Verify monetary fields are Decimal, tax is Decimal('0.00'), and total = subtotal + tax."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    service = SaaSInvoiceService(db_session)

    invoice = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="trial_conversion",
    )
    db_session.commit()

    assert isinstance(invoice.subtotal, Decimal)
    assert isinstance(invoice.tax_amount, Decimal)
    assert isinstance(invoice.total_amount, Decimal)
    assert invoice.tax_amount == Decimal("0.00")
    assert invoice.total_amount == invoice.subtotal + invoice.tax_amount


def test_initial_status_unpaid_and_paid_at_none(db_session: Session, sample_tenant_and_sub):
    """Verify initial invoice status is unpaid and paid_at is None."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    service = SaaSInvoiceService(db_session)

    invoice = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="subscription_cycle",
    )
    db_session.commit()

    assert invoice.status == "unpaid"
    assert invoice.paid_at is None


def test_billing_reason_validation(db_session: Session, sample_tenant_and_sub):
    """Verify invalid billing reason is rejected with AppException."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    service = SaaSInvoiceService(db_session)

    with pytest.raises(AppException) as exc_info:
        service.create_invoice(
            subscription_id=sub_id,
            billing_reason="invalid_billing_reason",
        )
    assert "Invalid billing reason" in str(exc_info.value)


def test_due_date_behavior(db_session: Session, sample_tenant_and_sub):
    """Verify custom due date or default to issuance timestamp."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    service = SaaSInvoiceService(db_session)

    custom_due = datetime(2026, 12, 31, 12, 0, 0)
    invoice = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="plan_upgrade",
        due_date=custom_due,
    )
    db_session.commit()

    assert invoice.due_date == custom_due


# ==============================================================================
# 2. INVOICE NUMBERING & SEQUENCE UNIQUENESS
# ==============================================================================


def test_invoice_number_format_and_sequence(db_session: Session):
    """Verify invoice number format INV-SAAS-{YYYY}-{00000} and strict sequence increments."""
    service = SaaSInvoiceService(db_session)
    year = 2030  # Use an isolated future year

    inv_num_1 = service.generate_invoice_number(year)
    inv_num_2 = service.generate_invoice_number(year)
    inv_num_3 = service.generate_invoice_number(year)
    db_session.commit()

    assert inv_num_1 == f"INV-SAAS-{year}-00001"
    assert inv_num_2 == f"INV-SAAS-{year}-00002"
    assert inv_num_3 == f"INV-SAAS-{year}-00003"


def test_invoice_duplicate_idempotency_protection(db_session: Session, sample_tenant_and_sub):
    """Verify duplicate invoice generation for same (subscription, billing_reason) is prevented."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    service = SaaSInvoiceService(db_session)

    # First creation
    inv1 = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="subscription_cycle",
    )
    db_session.commit()

    # Second creation with idempotent=True returns the same invoice
    inv2 = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="subscription_cycle",
        idempotent=True,
    )
    assert inv1.id == inv2.id
    assert inv1.invoice_number == inv2.invoice_number

    # Third creation with idempotent=False raises ConflictException
    with pytest.raises(ConflictException):
        service.create_invoice(
            subscription_id=sub_id,
            billing_reason="subscription_cycle",
            idempotent=False,
        )


# ==============================================================================
# 3. ISOLATION TESTS
# ==============================================================================


def test_no_pos_billing_modifications(db_session: Session, sample_tenant_and_sub):
    """Verify that SaaS invoice creation does NOT touch POS tables (invoices, sales, payments)."""
    sub_id = sample_tenant_and_sub["subscription_id"]
    tenant_id = sample_tenant_and_sub["tenant_id"]

    pos_invoices_before = db_session.query(Invoice).filter(Invoice.tenant_id == tenant_id).count()
    pos_sales_before = db_session.query(Sale).filter(Sale.tenant_id == tenant_id).count()
    pos_payments_before = db_session.query(Payment).filter(Payment.tenant_id == tenant_id).count()

    service = SaaSInvoiceService(db_session)
    invoice = service.create_invoice(
        subscription_id=sub_id,
        billing_reason="trial_conversion",
    )
    db_session.commit()

    pos_invoices_after = db_session.query(Invoice).filter(Invoice.tenant_id == tenant_id).count()
    pos_sales_after = db_session.query(Sale).filter(Sale.tenant_id == tenant_id).count()
    pos_payments_after = db_session.query(Payment).filter(Payment.tenant_id == tenant_id).count()

    assert pos_invoices_before == pos_invoices_after == 0
    assert pos_sales_before == pos_sales_after == 0
    assert pos_payments_before == pos_payments_after == 0
    assert invoice.id is not None
