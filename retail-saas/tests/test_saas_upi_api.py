"""
tests/test_saas_upi_api.py

P2 Task 5 — SaaS UPI API Integration Tests
Tests all HTTP endpoints for UPI checkout, UTR submission, and SA verification.
Validates:
- Authentication (401 for missing token)
- Tenant isolation (404 for cross-tenant access)
- Authorization (403 for tenant user on SA endpoints)
- Full happy-path flows (checkout → submit → verify/reject)
- Idempotent checkout reuse
- Concurrent verification
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.core.security import (
    create_access_token,
    create_super_admin_access_token,
    get_password_hash,
)
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSPlan,
    SaaSSubscription,
    SaaSUPITransaction,
)
from app.models.role import Role
from app.models.super_admin import SuperAdmin
from app.models.tenant import Tenant
from app.models.user import User
from app.services.saas_upi_service import _generate_reference


client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _setup_tenant_with_invoice(status="trialing", invoice_status="unpaid"):
    """Creates a complete tenant, plan, subscription, and invoice for testing."""
    db = SessionLocal()
    uid = _uid()
    try:
        plan = db.query(SaaSPlan).filter(SaaSPlan.code == "basic").first()

        tenant = Tenant(
            name=f"UPI Test Tenant {uid}",
            domain=f"upi-{uid}.test",
            is_active=True,
            plan="basic",
            subscription_status="trial",
        )
        db.add(tenant)
        db.flush()

        role = Role(
            tenant_id=tenant.id,
            name="admin",
            permissions=["*"],
            is_system=True,
        )
        db.add(role)
        db.flush()

        user = User(
            tenant_id=tenant.id,
            role_id=role.id,
            full_name="UPI Test User",
            email=f"upi-{uid}@test.com",
            hashed_password=get_password_hash("testpass"),
            is_active=True,
        )
        db.add(user)
        db.flush()

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

        import random
        inv_num = f"INV-SAAS-API-{random.randint(100000, 999999)}"
        invoice = SaaSInvoice(
            tenant_id=tenant.id,
            subscription_id=sub.id,
            invoice_number=inv_num,
            billing_reason="trial_conversion",
            subtotal=plan.price,
            tax_amount=Decimal("0.00"),
            total_amount=plan.price,
            currency=plan.currency,
            status=invoice_status,
            due_date=now,
            paid_at=None,
        )
        db.add(invoice)
        db.commit()
        db.refresh(tenant)
        db.refresh(user)
        db.refresh(sub)
        db.refresh(invoice)

        return db, tenant, user, sub, invoice
    except Exception:
        db.rollback()
        db.close()
        raise


def _make_super_admin(db):
    uid = _uid()
    sa = SuperAdmin(
        full_name=f"SA {uid}",
        email=f"sa-{uid}@admin.com",
        hashed_password=get_password_hash("sapass"),
        is_active=True,
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    return sa


def _user_token(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id), "tenant_id": user.tenant_id}
    )


def _sa_token(sa: SuperAdmin) -> str:
    return create_super_admin_access_token(
        data={"sub": str(sa.id), "role": "SUPERADMIN"}
    )


def _make_submitted_txn(db, tenant, sub, invoice):
    """Creates a submitted UPI transaction for testing verification flows."""
    ref = _generate_reference()
    txn = SaaSUPITransaction(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        invoice_id=invoice.id,
        reference=ref,
        utr=f"UTR-{_uid()}",
        amount=invoice.total_amount,
        currency=invoice.currency,
        status="submitted",
        upi_id="retailos@bank",
        submitted_at=datetime.utcnow(),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


# ---------------------------------------------------------------------------
# Authentication — all endpoints require auth
# ---------------------------------------------------------------------------

class TestAuthentication:
    def test_checkout_preview_requires_auth(self):
        resp = client.get("/api/v1/saas-billing/upi/checkout-preview")
        assert resp.status_code == 401

    def test_initiate_requires_auth(self):
        resp = client.post("/api/v1/saas-billing/upi/initiate?invoice_id=1")
        assert resp.status_code == 401

    def test_submit_requires_auth(self):
        resp = client.post("/api/v1/saas-billing/upi/submit", json={"reference": "x", "utr": "y"})
        assert resp.status_code == 401

    def test_get_transaction_requires_auth(self):
        resp = client.get("/api/v1/saas-billing/upi/transactions/UPIS-20260923-XXXXXXXX")
        assert resp.status_code == 401

    def test_qr_code_requires_auth(self):
        resp = client.get("/api/v1/saas-billing/upi/qr-code?reference=UPIS-20260923-XXXXXXXX")
        assert resp.status_code == 401

    def test_qr_image_requires_auth(self):
        resp = client.get("/api/v1/saas-billing/upi/qr-image?reference=UPIS-20260923-XXXXXXXX")
        assert resp.status_code == 401

    def test_sa_list_requires_sa_auth(self):
        resp = client.get("/api/v1/super-admins/upi-transactions")
        assert resp.status_code == 401

    def test_sa_verify_requires_sa_auth(self):
        resp = client.post("/api/v1/super-admins/upi-transactions/UPIS-FAKE/verify")
        assert resp.status_code == 401

    def test_sa_reject_requires_sa_auth(self):
        resp = client.post(
            "/api/v1/super-admins/upi-transactions/UPIS-FAKE/reject",
            json={"rejection_reason": "Testing auth"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Authorization — tenant user cannot call SA endpoints
# ---------------------------------------------------------------------------

class TestAuthorization:
    def test_tenant_user_cannot_verify(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)
            token = _user_token(user)
            resp = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 401
        finally:
            db.close()

    def test_tenant_user_cannot_reject(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)
            token = _user_token(user)
            resp = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/reject",
                json={"rejection_reason": "Unauthorized attempt"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 401
        finally:
            db.close()

    def test_tenant_user_cannot_list_all_transactions(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            resp = client.get(
                "/api/v1/super-admins/upi-transactions",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 401
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Checkout preview
# ---------------------------------------------------------------------------

class TestAPICheckoutPreview:
    def test_returns_200_with_payable_invoice(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            resp = client.get(
                "/api/v1/saas-billing/upi/checkout-preview",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["invoice_id"] == invoice.id
            assert str(data["amount"]) == str(invoice.total_amount)
            assert data["currency"] == "INR"
            assert data["subscription_id"] == sub.id
        finally:
            db.close()

    def test_returns_404_when_no_payable_invoice(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(invoice_status="paid")
        try:
            token = _user_token(user)
            resp = client.get(
                "/api/v1/saas-billing/upi/checkout-preview",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 404
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Initiate checkout
# ---------------------------------------------------------------------------

class TestAPIInitiateCheckout:
    def test_creates_pending_transaction(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            resp = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "pending"
            assert data["reference"].startswith("UPIS-")
            assert data["invoice_id"] == invoice.id
        finally:
            db.close()

    def test_idempotent_within_window(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            r1 = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            r2 = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r1.status_code == 201
            assert r2.status_code == 201
            assert r1.json()["reference"] == r2.json()["reference"]
        finally:
            db.close()

    def test_cross_tenant_invoice_raises_404(self):
        db_a, ta, ua, sub_a, inv_a = _setup_tenant_with_invoice()
        db_b, tb, ub, sub_b, inv_b = _setup_tenant_with_invoice()
        try:
            token_a = _user_token(ua)
            resp = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={inv_b.id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert resp.status_code == 404
        finally:
            db_a.close()
            db_b.close()


# ---------------------------------------------------------------------------
# Submit UTR
# ---------------------------------------------------------------------------

class TestAPISubmitUTR:
    def test_pending_to_submitted(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            # Initiate first
            init_resp = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            reference = init_resp.json()["reference"]

            utr = f"UTR{_uid()}"
            resp = client.post(
                "/api/v1/saas-billing/upi/submit",
                json={"reference": reference, "utr": utr},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "submitted"
            assert data["utr"] == utr
        finally:
            db.close()

    def test_duplicate_utr_returns_409(self):
        db_a, ta, ua, sub_a, inv_a = _setup_tenant_with_invoice()
        db_b, tb, ub, sub_b, inv_b = _setup_tenant_with_invoice()
        try:
            token_a = _user_token(ua)
            token_b = _user_token(ub)
            shared_utr = f"DUPUTR{_uid()}"

            # Tenant A submits UTR
            init_a = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={inv_a.id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            ref_a = init_a.json()["reference"]
            client.post(
                "/api/v1/saas-billing/upi/submit",
                json={"reference": ref_a, "utr": shared_utr},
                headers={"Authorization": f"Bearer {token_a}"},
            )

            # Tenant B tries same UTR
            init_b = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={inv_b.id}",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            ref_b = init_b.json()["reference"]
            resp = client.post(
                "/api/v1/saas-billing/upi/submit",
                json={"reference": ref_b, "utr": shared_utr},
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert resp.status_code == 409
        finally:
            db_a.close()
            db_b.close()

    def test_cross_tenant_submit_raises_404(self):
        db_a, ta, ua, sub_a, inv_a = _setup_tenant_with_invoice()
        db_b, tb, ub, sub_b, inv_b = _setup_tenant_with_invoice()
        try:
            token_b = _user_token(ub)
            # Tenant A initiates
            token_a = _user_token(ua)
            init_a = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={inv_a.id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            ref_a = init_a.json()["reference"]

            # Tenant B tries to submit for Tenant A's reference
            resp = client.post(
                "/api/v1/saas-billing/upi/submit",
                json={"reference": ref_a, "utr": f"CROSSUTR{_uid()}"},
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert resp.status_code == 404
        finally:
            db_a.close()
            db_b.close()


# ---------------------------------------------------------------------------
# Transaction status
# ---------------------------------------------------------------------------

class TestAPITransactionStatus:
    def test_get_own_transaction(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            init_resp = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            ref = init_resp.json()["reference"]

            resp = client.get(
                f"/api/v1/saas-billing/upi/transactions/{ref}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["reference"] == ref
        finally:
            db.close()

    def test_cross_tenant_transaction_returns_404(self):
        db_a, ta, ua, sub_a, inv_a = _setup_tenant_with_invoice()
        db_b, tb, ub, sub_b, inv_b = _setup_tenant_with_invoice()
        try:
            token_a = _user_token(ua)
            token_b = _user_token(ub)

            init_a = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={inv_a.id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            ref_a = init_a.json()["reference"]

            resp = client.get(
                f"/api/v1/saas-billing/upi/transactions/{ref_a}",
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert resp.status_code == 404
        finally:
            db_a.close()
            db_b.close()


# ---------------------------------------------------------------------------
# QR code
# ---------------------------------------------------------------------------

class TestAPIQRCode:
    def test_returns_qr_payload(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            init_resp = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            ref = init_resp.json()["reference"]

            resp = client.get(
                f"/api/v1/saas-billing/upi/qr-code?reference={ref}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "upi://pay?" in data["upi_payload"]
            assert data["qr_image_base64"]  # non-empty base64 string
            assert data["reference"] == ref
        finally:
            db.close()

    def test_returns_qr_image_png(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            init_resp = client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            ref = init_resp.json()["reference"]

            resp = client.get(
                f"/api/v1/saas-billing/upi/qr-image?reference={ref}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/png"
            assert resp.content.startswith(b"\x89PNG")
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Super Admin: List transactions
# ---------------------------------------------------------------------------

class TestSAListTransactions:
    def test_sa_can_list_transactions(self):
        db_sa = SessionLocal()
        sa = _make_super_admin(db_sa)
        db_sa.close()

        db, tenant, user, sub, invoice = _setup_tenant_with_invoice()
        try:
            token = _user_token(user)
            client.post(
                f"/api/v1/saas-billing/upi/initiate?invoice_id={invoice.id}",
                headers={"Authorization": f"Bearer {token}"},
            )

            sa_db = SessionLocal()
            sa_ref = sa_db.query(SuperAdmin).filter(SuperAdmin.id == sa.id).first()
            sa_token = _sa_token(sa_ref)
            sa_db.close()

            resp = client.get(
                "/api/v1/super-admins/upi-transactions",
                headers={"Authorization": f"Bearer {sa_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
        finally:
            db.close()

    def test_sa_filter_by_status(self):
        db_sa = SessionLocal()
        sa = _make_super_admin(db_sa)
        sa_db_token = _sa_token(sa)
        db_sa.close()

        resp = client.get(
            "/api/v1/super-admins/upi-transactions?status=verified",
            headers={"Authorization": f"Bearer {sa_db_token}"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Super Admin: Verify
# ---------------------------------------------------------------------------

class TestSAVerify:
    def test_sa_verifies_transaction(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            resp = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {sa_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "verified"
            assert data["verified_by_super_admin_id"] == sa.id
        finally:
            db.close()

    def test_concurrent_verify_only_one_succeeds(self):
        """
        Simulate concurrent verification by verifying twice in sequence.
        The second attempt should get 409.
        """
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            r1 = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {sa_token}"},
            )
            r2 = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {sa_token}"},
            )

            assert r1.status_code == 200
            assert r2.status_code == 409
        finally:
            db.close()

    def test_genuine_concurrent_verify_parallel_threads(self):
        """
        True concurrent verification using ThreadPoolExecutor.
        Two concurrent threads attempt to verify the exact same reference simultaneously.
        Atomic conditional row-level transition guarantees exactly one succeeds (200)
        and exactly one fails with Conflict (409).
        """
        import concurrent.futures
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)
            ref = str(txn.reference)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            def post_verify():
                return client.post(
                    f"/api/v1/super-admins/upi-transactions/{ref}/verify",
                    headers={"Authorization": f"Bearer {sa_token}"},
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(post_verify)
                f2 = executor.submit(post_verify)
                r1 = f1.result()
                r2 = f2.result()

            status_codes = sorted([r1.status_code, r2.status_code])
            assert status_codes == [200, 409], f"Expected [200, 409], got {status_codes}"

            # Verify invoice is paid exactly once
            db.refresh(invoice)
            assert invoice.status == "paid"
            assert invoice.paid_at is not None
        finally:
            db.close()

    def test_cancelled_subscription_verification_fails(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="cancelled")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            resp = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {sa_token}"},
            )
            assert resp.status_code == 400
        finally:
            db.close()

    def test_verify_updates_invoice_to_paid(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {sa_token}"},
            )

            db.refresh(invoice)
            assert invoice.status == "paid"
            assert invoice.paid_at is not None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Super Admin: Reject
# ---------------------------------------------------------------------------

class TestSAReject:
    def test_sa_rejects_transaction(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            resp = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/reject",
                json={"rejection_reason": "UTR not found in bank portal"},
                headers={"Authorization": f"Bearer {sa_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "rejected"
            assert "UTR not found" in data["rejection_reason"]
        finally:
            db.close()

    def test_rejection_leaves_invoice_unpaid(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/reject",
                json={"rejection_reason": "Invalid UTR provided"},
                headers={"Authorization": f"Bearer {sa_token}"},
            )

            db.refresh(invoice)
            assert invoice.status == "unpaid"
            assert invoice.paid_at is None
        finally:
            db.close()

    def test_reject_reason_too_short_returns_422(self):
        db, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db, tenant, sub, invoice)

            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            resp = client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/reject",
                json={"rejection_reason": "Bad"},  # < 5 chars
                headers={"Authorization": f"Bearer {sa_token}"},
            )
            assert resp.status_code == 422
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Historical integrity
# ---------------------------------------------------------------------------

class TestAPIHistoricalIntegrity:
    def test_no_pos_table_modifications(self):
        """Verify the POS payments table is untouched by UPI operations."""
        from app.models.payment import Payment
        db = SessionLocal()
        try:
            initial_count = db.query(Payment).count()
        finally:
            db.close()

        # Run a full verify flow
        db2, tenant, user, sub, invoice = _setup_tenant_with_invoice(status="trialing")
        try:
            txn = _make_submitted_txn(db2, tenant, sub, invoice)
            db_sa = SessionLocal()
            sa = _make_super_admin(db_sa)
            sa_token = _sa_token(sa)
            db_sa.close()

            client.post(
                f"/api/v1/super-admins/upi-transactions/{txn.reference}/verify",
                headers={"Authorization": f"Bearer {sa_token}"},
            )
        finally:
            db2.close()

        db3 = SessionLocal()
        try:
            final_count = db3.query(Payment).count()
        finally:
            db3.close()

        assert final_count == initial_count
