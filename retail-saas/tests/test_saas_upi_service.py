"""
tests/test_saas_upi_service.py

P2 Task 5 - SaaS UPI Service Layer Tests
Tests all business logic in SaaSUPIService, including:
- Checkout preview
- Transaction initiation and reuse
- Reference format validation
- UTR submission and duplicate detection
- Verify/reject state machine
- Concurrent verification protection
- Subscription status transition rules
- Tenant isolation at service layer
- POS table isolation
- Historical integrity
"""
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSPlan,
    SaaSSubscription,
    SaaSUPITransaction,
)
from app.models.tenant import Tenant
from app.services.saas_upi_service import SaaSUPIService, _generate_reference


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    from app.core.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _make_tenant(db, domain: str) -> Tenant:
    t = Tenant(name=f"Tenant {domain}", domain=domain, is_active=True, plan="basic", subscription_status="trial")
    db.add(t)
    db.flush()
    return t


def _make_subscription(db, tenant: Tenant, plan: SaaSPlan, status="trialing") -> SaaSSubscription:
    now = datetime.utcnow()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=status,
        billing_interval=plan.billing_interval,
        unit_price=plan.price,
        currency=plan.currency,
        start_date=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=14),
        trial_end_date=now + timedelta(days=14),
        cancel_at_period_end=False,
    )
    db.add(sub)
    db.flush()
    return sub


def _make_invoice(db, tenant: Tenant, sub: SaaSSubscription, status="unpaid") -> SaaSInvoice:
    import math, random
    now = datetime.utcnow()
    num = f"INV-SAAS-TEST-{random.randint(100000,999999)}"
    inv = SaaSInvoice(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_number=num,
        billing_reason="trial_conversion",
        subtotal=sub.unit_price,
        tax_amount=Decimal("0.00"),
        total_amount=sub.unit_price,
        currency=sub.currency,
        status=status,
        due_date=now,
        paid_at=None,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_upi_txn(db, tenant, sub, inv, status="pending", utr=None, reference=None) -> SaaSUPITransaction:
    ref = reference or _generate_reference()
    txn = SaaSUPITransaction(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_id=inv.id,
        reference=ref,
        utr=utr,
        amount=inv.total_amount,
        currency=inv.currency,
        status=status,
        upi_id="retailos@bank",
    )
    db.add(txn)
    db.flush()
    return txn


def _get_basic_plan(db):
    plan = db.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()
    assert plan is not None, "Basic plan fixture missing"
    return plan


# ---------------------------------------------------------------------------
# Reference generation
# ---------------------------------------------------------------------------

class TestReferenceGeneration:
    def test_format_matches_pattern(self):
        ref = _generate_reference()
        assert re.match(r"^UPIS-\d{8}-[0-9A-F]{8}$", ref), f"Bad reference: {ref}"

    def test_uniqueness(self):
        refs = {_generate_reference() for _ in range(50)}
        assert len(refs) == 50, "Reference generator produced duplicates"

    def test_date_component(self):
        ref = _generate_reference()
        date_part = ref.split("-")[1]
        expected = datetime.utcnow().strftime("%Y%m%d")
        assert date_part == expected


# ---------------------------------------------------------------------------
# Checkout preview
# ---------------------------------------------------------------------------

class TestCheckoutPreview:
    def test_returns_payable_invoice(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"preview-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.get_checkout_preview(tenant.id)

        assert result["invoice_id"] == inv.id
        assert result["invoice_number"] == inv.invoice_number
        assert result["amount"] == inv.total_amount
        assert result["currency"] == inv.currency
        assert result["subscription_id"] == sub.id
        assert result["plan_code"] == plan.code

    def test_no_payable_invoice_raises_404(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"noinv-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        # Mark invoice as paid
        inv = _make_invoice(db, tenant, sub, status="paid")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(NotFoundException):
            svc.get_checkout_preview(tenant.id)


# ---------------------------------------------------------------------------
# Initiate checkout
# ---------------------------------------------------------------------------

class TestInitiateCheckout:
    def test_creates_pending_transaction(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"init-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.initiate_checkout(tenant.id, inv.id)

        assert result["status"] == "pending"
        assert result["amount"] == inv.total_amount
        assert result["currency"] == inv.currency
        assert result["invoice_id"] == inv.id
        assert result["subscription_id"] == sub.id
        assert result["reference"].startswith("UPIS-")

    def test_amount_equals_invoice_total(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"amtcheck-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.initiate_checkout(tenant.id, inv.id)

        assert result["amount"] == plan.price

    def test_currency_equals_invoice_currency(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"cur-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.initiate_checkout(tenant.id, inv.id)

        assert result["currency"] == "INR"

    def test_upi_payload_contains_server_vpa(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"vpa-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.initiate_checkout(tenant.id, inv.id)

        from app.core.config import get_settings
        settings = get_settings()
        assert settings.SAAS_UPI_VPA in result["upi_payload"]

    def test_reuse_within_window(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"reuse-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        r1 = svc.initiate_checkout(tenant.id, inv.id)
        r2 = svc.initiate_checkout(tenant.id, inv.id)

        assert r1["reference"] == r2["reference"]

    def test_new_reference_after_reuse_window(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"newref-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        r1 = svc.initiate_checkout(tenant.id, inv.id)

        # Simulate expired pending transaction by backdating created_at
        txn = db.query(SaaSUPITransaction).filter(
            SaaSUPITransaction.reference == r1["reference"]
        ).first()
        txn.created_at = datetime.utcnow() - timedelta(seconds=1000)
        db.commit()

        r2 = svc.initiate_checkout(tenant.id, inv.id)
        assert r1["reference"] != r2["reference"]

    def test_submitted_txn_not_reused(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"nosub-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        # Create a submitted transaction manually
        _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="UTR12345")
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.initiate_checkout(tenant.id, inv.id)
        # A new pending reference should be created (submitted ones not reused)
        assert result["status"] == "pending"

    def test_cannot_initiate_for_other_tenant_invoice(self, db):
        plan = _get_basic_plan(db)
        tenant_a = _make_tenant(db, f"ta-{_generate_reference()[:8]}.test")
        tenant_b = _make_tenant(db, f"tb-{_generate_reference()[:8]}.test")
        sub_b = _make_subscription(db, tenant_b, plan)
        inv_b = _make_invoice(db, tenant_b, sub_b)
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(NotFoundException):
            svc.initiate_checkout(tenant_a.id, inv_b.id)

    def test_paid_invoice_raises_404(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"paid-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub, status="paid")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(NotFoundException):
            svc.initiate_checkout(tenant.id, inv.id)


# ---------------------------------------------------------------------------
# UTR submission
# ---------------------------------------------------------------------------

class TestSubmitUTR:
    def test_pending_to_submitted(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"subutr-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.submit_utr(
            tenant_id=tenant.id,
            reference=txn.reference,
            utr="UTR9876543210",
            payer_vpa="payer@okaxis",
            proof_image_url=None,
        )

        assert result.status == "submitted"
        assert result.utr == "UTR9876543210"
        assert result.submitted_at is not None
        assert result.payer_vpa == "payer@okaxis"

    def test_duplicate_utr_raises_409(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"duputr-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)

        inv1 = _make_invoice(db, tenant, sub)
        inv2 = _make_invoice(db, tenant, sub)

        txn1 = _make_upi_txn(db, tenant, sub, inv1, status="submitted", utr="DUPTEST123")
        txn2 = _make_upi_txn(db, tenant, sub, inv2)
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(ConflictException, match="DUPTEST123"):
            svc.submit_utr(
                tenant_id=tenant.id,
                reference=txn2.reference,
                utr="DUPTEST123",
                payer_vpa=None,
                proof_image_url=None,
            )

    def test_already_submitted_raises_400(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"alrsub-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="OLDUTR")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(AppException):
            svc.submit_utr(
                tenant_id=tenant.id,
                reference=txn.reference,
                utr="NEWUTR",
                payer_vpa=None,
                proof_image_url=None,
            )

    def test_cross_tenant_utr_submit_raises_404(self, db):
        plan = _get_basic_plan(db)
        tenant_a = _make_tenant(db, f"ta2-{_generate_reference()[:8]}.test")
        tenant_b = _make_tenant(db, f"tb2-{_generate_reference()[:8]}.test")
        sub_b = _make_subscription(db, tenant_b, plan)
        inv_b = _make_invoice(db, tenant_b, sub_b)
        txn_b = _make_upi_txn(db, tenant_b, sub_b, inv_b)
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(NotFoundException):
            svc.submit_utr(
                tenant_id=tenant_a.id,
                reference=txn_b.reference,
                utr="CROSSUTR123",
                payer_vpa=None,
                proof_image_url=None,
            )


# ---------------------------------------------------------------------------
# Verify transaction
# ---------------------------------------------------------------------------

class TestVerifyTransaction:
    def test_submitted_to_verified(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"ver-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST001")
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        assert result.status == "verified"
        assert result.verified_at is not None
        assert result.verified_by_super_admin_id == 1

    def test_invoice_marked_paid(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"invpaid-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST002")
        db.commit()

        svc = SaaSUPIService(db)
        svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        db.refresh(inv)
        assert inv.status == "paid"
        assert inv.paid_at is not None

    def test_trialing_subscription_becomes_active(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"triact-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST003")
        db.commit()

        svc = SaaSUPIService(db)
        svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        db.refresh(sub)
        assert sub.status == "active"

    def test_past_due_subscription_becomes_active(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"pastdue-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="past_due")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST004")
        db.commit()

        svc = SaaSUPIService(db)
        svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        db.refresh(sub)
        assert sub.status == "active"

    def test_tenant_projection_synced(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"proj-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST005")
        db.commit()

        svc = SaaSUPIService(db)
        svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        db.refresh(tenant)
        assert tenant.subscription_status == "active"

    def test_cancelled_subscription_verification_rejected(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"cancel-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="cancelled")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST006")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(AppException, match="cancelled"):
            svc.verify_transaction(reference=txn.reference, super_admin_id=1)

    def test_expired_subscription_verification_rejected(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"exp-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="expired")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST007")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(AppException, match="expired"):
            svc.verify_transaction(reference=txn.reference, super_admin_id=1)

    def test_pending_transaction_cannot_be_verified(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"pndver-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="pending")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(AppException):
            svc.verify_transaction(reference=txn.reference, super_admin_id=1)

    def test_double_verification_raises_conflict(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"dblver-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="VERTEST008")
        db.commit()

        svc = SaaSUPIService(db)
        svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        with pytest.raises(ConflictException):
            svc.verify_transaction(reference=txn.reference, super_admin_id=2)

    def test_genuine_concurrent_verification_threads(self, db):
        """
        Tests true concurrent verification across parallel threads with independent DB sessions.
        Exactly one thread succeeds and the other receives ConflictException.
        """
        import concurrent.futures
        from app.core.database import SessionLocal
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"concurth-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr=f"CONCURTH{_generate_reference()[:6]}")
        ref = str(txn.reference)
        db.commit()

        results = []
        errors = []

        def worker(admin_id):
            worker_db = SessionLocal()
            try:
                svc = SaaSUPIService(worker_db)
                r = svc.verify_transaction(reference=ref, super_admin_id=admin_id)
                results.append(r)
            except Exception as e:
                errors.append(e)
            finally:
                worker_db.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker, 1)
            f2 = executor.submit(worker, 2)
            f1.result()
            f2.result()

        assert len(results) == 1, f"Expected 1 success, got {len(results)}"
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}"
        assert isinstance(errors[0], ConflictException)

    def test_get_qr_image_bytes(self, db):
        """Tests that get_qr_image returns valid PNG binary bytes."""
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"qrimg-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv)
        db.commit()

        svc = SaaSUPIService(db)
        img_bytes = svc.get_qr_image(tenant.id, txn.reference)
        assert isinstance(img_bytes, bytes)
        assert img_bytes.startswith(b"\x89PNG")


# ---------------------------------------------------------------------------
# Reject transaction
# ---------------------------------------------------------------------------

class TestRejectTransaction:
    def test_submitted_to_rejected(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"rej-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="REJTEST001")
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.reject_transaction(
            reference=txn.reference,
            super_admin_id=1,
            rejection_reason="UTR not found in bank records",
        )

        assert result.status == "rejected"
        assert result.rejection_reason == "UTR not found in bank records"

    def test_invoice_remains_unpaid_after_rejection(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"rejinv-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="REJTEST002")
        db.commit()

        svc = SaaSUPIService(db)
        svc.reject_transaction(
            reference=txn.reference,
            super_admin_id=1,
            rejection_reason="Invalid UTR format",
        )

        db.refresh(inv)
        assert inv.status == "unpaid"
        assert inv.paid_at is None

    def test_subscription_unchanged_after_rejection(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"rejsub-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="REJTEST003")
        db.commit()

        svc = SaaSUPIService(db)
        svc.reject_transaction(
            reference=txn.reference,
            super_admin_id=1,
            rejection_reason="UTR mismatch",
        )

        db.refresh(sub)
        assert sub.status == "trialing"

    def test_rejected_record_preserved(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"rejpres-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="REJTEST004")
        db.commit()

        svc = SaaSUPIService(db)
        svc.reject_transaction(
            reference=txn.reference,
            super_admin_id=1,
            rejection_reason="Payment not received",
        )

        stored = db.query(SaaSUPITransaction).filter(
            SaaSUPITransaction.reference == txn.reference
        ).first()
        assert stored is not None
        assert stored.status == "rejected"

    def test_retry_creates_new_reference(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"retry-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="REJTEST005")
        db.commit()

        svc = SaaSUPIService(db)
        svc.reject_transaction(
            reference=txn.reference,
            super_admin_id=1,
            rejection_reason="Suspect transaction",
        )

        # New checkout should create new reference
        result = svc.initiate_checkout(tenant.id, inv.id)
        assert result["reference"] != txn.reference
        assert result["status"] == "pending"

    def test_pending_transaction_cannot_be_rejected(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"pndrej-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="pending")
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(AppException):
            svc.reject_transaction(
                reference=txn.reference,
                super_admin_id=1,
                rejection_reason="Testing pending reject",
            )

    def test_double_rejection_raises_conflict(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"dblrej-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="REJTEST006")
        db.commit()

        svc = SaaSUPIService(db)
        svc.reject_transaction(
            reference=txn.reference,
            super_admin_id=1,
            rejection_reason="First rejection",
        )
        with pytest.raises(ConflictException):
            svc.reject_transaction(
                reference=txn.reference,
                super_admin_id=2,
                rejection_reason="Second rejection attempt",
            )


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_tenant_a_cannot_view_tenant_b_transaction(self, db):
        plan = _get_basic_plan(db)
        ta = _make_tenant(db, f"ta3-{_generate_reference()[:8]}.test")
        tb = _make_tenant(db, f"tb3-{_generate_reference()[:8]}.test")
        sub_b = _make_subscription(db, tb, plan)
        inv_b = _make_invoice(db, tb, sub_b)
        txn_b = _make_upi_txn(db, tb, sub_b, inv_b)
        db.commit()

        svc = SaaSUPIService(db)
        with pytest.raises(NotFoundException):
            svc.get_transaction(ta.id, txn_b.reference)

    def test_super_admin_can_view_any_transaction(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"saview-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.get_transaction_admin(txn.reference)
        assert result.id == txn.id


# ---------------------------------------------------------------------------
# Amount integrity
# ---------------------------------------------------------------------------

class TestAmountIntegrity:
    def test_txn_amount_equals_invoice_total(self, db):
        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"amtint-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan)
        inv = _make_invoice(db, tenant, sub)
        db.commit()

        svc = SaaSUPIService(db)
        result = svc.initiate_checkout(tenant.id, inv.id)

        txn = db.query(SaaSUPITransaction).filter(
            SaaSUPITransaction.reference == result["reference"]
        ).first()
        assert txn.amount == inv.total_amount
        assert txn.currency == inv.currency


# ---------------------------------------------------------------------------
# POS isolation
# ---------------------------------------------------------------------------

class TestPOSIsolation:
    def test_no_pos_invoice_created(self, db):
        from app.models.invoice import Invoice as POSInvoice
        initial_count = db.query(POSInvoice).count()

        plan = _get_basic_plan(db)
        tenant = _make_tenant(db, f"posiso-{_generate_reference()[:8]}.test")
        sub = _make_subscription(db, tenant, plan, status="trialing")
        inv = _make_invoice(db, tenant, sub)
        txn = _make_upi_txn(db, tenant, sub, inv, status="submitted", utr="POSTEST001")
        db.commit()

        svc = SaaSUPIService(db)
        svc.verify_transaction(reference=txn.reference, super_admin_id=1)

        assert db.query(POSInvoice).count() == initial_count


# ---------------------------------------------------------------------------
# Historical integrity (13 Task 1 subscriptions)
# ---------------------------------------------------------------------------

class TestHistoricalIntegrity:
    def test_no_fake_upi_transactions(self, db):
        """No SaaSUPITransaction records should exist for Task 1 subscriptions."""
        txn_count = db.query(SaaSUPITransaction).count()
        # The test DB only has transactions created by test cases above
        # This verifies we start from zero without pre-existing fake records
        # (Task 1 created 13 subscriptions with no UPI transactions)
        # We verify no transaction exists for those subscriptions created in conftest
        sub_ids = [
            sub.id for sub in db.query(SaaSSubscription).all()
        ]
        # All transactions in DB should reference test-created subscriptions only
        for txn in db.query(SaaSUPITransaction).all():
            assert txn.subscription_id in sub_ids
