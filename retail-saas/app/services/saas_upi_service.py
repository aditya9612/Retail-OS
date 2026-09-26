import base64
import io
import math
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from urllib.parse import quote

from dateutil.relativedelta import relativedelta
import qrcode
from reportlab.lib.utils import ImageReader
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
)
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSSubscription,
    SaaSUPITransaction,
)
from app.services.saas_subscription_service import SaaSSubscriptionService


settings = get_settings()

# Status constants
PENDING = "pending"
SUBMITTED = "submitted"
VERIFIED = "verified"
REJECTED = "rejected"

# Subscriptions that may transition to active on successful payment
VERIFIABLE_SUBSCRIPTION_STATUSES = ["trialing", "active", "past_due"]
TERMINAL_SUBSCRIPTION_STATUSES = ["cancelled", "expired"]

# Invoices eligible for UPI checkout
PAYABLE_INVOICE_STATUSES = ["unpaid"]


def _generate_reference() -> str:
    """
    Generates a cryptographically unique UPI reference in the format:
      UPIS-{YYYYMMDD}-{8_HEX_CHARS}
    Uses secrets.token_hex(4) which returns exactly 8 hex characters.
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix = secrets.token_hex(4).upper()
    return f"UPIS-{date_str}-{suffix}"


def _build_upi_payload(
    vpa: str,
    payee_name: str,
    amount: Decimal,
    currency: str,
    txn_note: str,
) -> str:
    """
    Builds a UPI deep-link string per UPI standards:
      upi://pay?pa={VPA}&pn={NAME}&am={AMOUNT}&cu={CURRENCY}&tn={NOTE}
    """
    encoded_name = quote(payee_name)
    encoded_note = quote(txn_note)
    return (
        f"upi://pay?pa={vpa}"
        f"&pn={encoded_name}"
        f"&am={amount:.2f}"
        f"&cu={currency}"
        f"&tn={encoded_note}"
    )


def _build_qr_image_bytes(upi_payload: str) -> bytes:
    """
    Generates a QR code PNG from the UPI payload and returns raw image bytes.
    Uses the qrcode==8.2 library already installed in the project.
    """
    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(upi_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_qr_image_base64(upi_payload: str) -> str:
    """
    Generates a QR code PNG from the UPI payload and returns it as a
    base64-encoded string (no data-URI prefix).
    """
    img_bytes = _build_qr_image_bytes(upi_payload)
    return base64.b64encode(img_bytes).decode("utf-8")


class SaaSUPIService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Tenant-facing
    # ------------------------------------------------------------------

    def get_checkout_preview(self, tenant_id: int) -> dict:
        """
        Returns the current payable invoice and subscription context
        for a tenant. Raises NotFoundException if no payable invoice exists.
        """
        invoice = self._get_payable_invoice(tenant_id)
        subscription = self._get_subscription(invoice.subscription_id, tenant_id)
        plan = subscription.plan

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "amount": invoice.total_amount,
            "currency": invoice.currency,
            "due_date": invoice.due_date,
            "subscription_id": subscription.id,
            "plan_code": plan.code,
            "plan_name": plan.name,
            "subscription_status": subscription.status,
        }

    def initiate_checkout(self, tenant_id: int, invoice_id: int) -> dict:
        """
        Creates or reuses a pending UPI transaction for the given invoice.

        Reuse rule: if a 'pending' transaction for the same invoice exists
        within the configured SAAS_UPI_CHECKOUT_REUSE_WINDOW_SECONDS, it is
        returned without creating a new record.

        Only pending transactions are reused. submitted, verified, and
        rejected transactions are NEVER reused as new checkouts.

        Returns a dict suitable for UPIInitiateResponse.
        """
        # Verify invoice belongs to this tenant and is payable
        invoice = (
            self.db.query(SaaSInvoice)
            .filter(
                SaaSInvoice.id == invoice_id,
                SaaSInvoice.tenant_id == tenant_id,
                SaaSInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
            )
            .first()
        )
        if not invoice:
            raise NotFoundException(
                "No payable invoice found. The invoice may not exist, "
                "belong to another tenant, or may already be paid."
            )

        subscription = self._get_subscription(invoice.subscription_id, tenant_id)

        # Check for an existing pending transaction within the reuse window
        reuse_cutoff = datetime.utcnow() - timedelta(
            seconds=settings.SAAS_UPI_CHECKOUT_REUSE_WINDOW_SECONDS
        )
        existing = (
            self.db.query(SaaSUPITransaction)
            .filter(
                SaaSUPITransaction.invoice_id == invoice_id,
                SaaSUPITransaction.tenant_id == tenant_id,
                SaaSUPITransaction.status == PENDING,
                SaaSUPITransaction.created_at >= reuse_cutoff,
            )
            .order_by(SaaSUPITransaction.created_at.desc())
            .first()
        )

        if existing:
            upi_payload = _build_upi_payload(
                vpa=settings.SAAS_UPI_VPA,
                payee_name=settings.SAAS_UPI_PAYEE_NAME,
                amount=existing.amount,
                currency=existing.currency,
                txn_note=f"SaaS Invoice {invoice.invoice_number}",
            )
            return {
                "reference": existing.reference,
                "amount": existing.amount,
                "currency": existing.currency,
                "upi_vpa": settings.SAAS_UPI_VPA,
                "upi_payload": upi_payload,
                "invoice_id": invoice.id,
                "subscription_id": subscription.id,
                "status": existing.status,
                "created_at": existing.created_at,
            }

        # Create a new pending transaction
        reference = _generate_reference()
        upi_payload = _build_upi_payload(
            vpa=settings.SAAS_UPI_VPA,
            payee_name=settings.SAAS_UPI_PAYEE_NAME,
            amount=invoice.total_amount,
            currency=invoice.currency,
            txn_note=f"SaaS Invoice {invoice.invoice_number}",
        )

        txn = SaaSUPITransaction(
            tenant_id=tenant_id,
            subscription_id=subscription.id,
            invoice_id=invoice.id,
            reference=reference,
            utr=None,
            amount=invoice.total_amount,    # Server-authoritative amount
            currency=invoice.currency,      # Server-authoritative currency
            status=PENDING,
            upi_id=settings.SAAS_UPI_VPA,
            payer_vpa=None,
            submitted_at=None,
            verified_at=None,
            verified_by_super_admin_id=None,
            rejection_reason=None,
            proof_image_url=None,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)

        return {
            "reference": txn.reference,
            "amount": txn.amount,
            "currency": txn.currency,
            "upi_vpa": settings.SAAS_UPI_VPA,
            "upi_payload": upi_payload,
            "invoice_id": invoice.id,
            "subscription_id": subscription.id,
            "status": txn.status,
            "created_at": txn.created_at,
        }

    def get_qr_code(self, tenant_id: int, reference: str) -> dict:
        """
        Returns UPI deep-link payload and base64-encoded QR PNG for a
        pending or submitted transaction. Enforces tenant isolation.
        """
        txn = self._get_txn_for_tenant(tenant_id, reference)

        upi_payload = _build_upi_payload(
            vpa=settings.SAAS_UPI_VPA,
            payee_name=settings.SAAS_UPI_PAYEE_NAME,
            amount=txn.amount,
            currency=txn.currency,
            txn_note=f"SaaS Ref {reference}",
        )
        qr_b64 = _build_qr_image_base64(upi_payload)

        return {
            "reference": reference,
            "upi_payload": upi_payload,
            "qr_image_base64": qr_b64,
            "amount": txn.amount,
            "currency": txn.currency,
            "upi_vpa": settings.SAAS_UPI_VPA,
        }

    def get_qr_image(self, tenant_id: int, reference: str) -> bytes:
        """
        Returns raw PNG QR image bytes for scanning.
        Enforces tenant isolation.
        """
        txn = self._get_txn_for_tenant(tenant_id, reference)

        upi_payload = _build_upi_payload(
            vpa=settings.SAAS_UPI_VPA,
            payee_name=settings.SAAS_UPI_PAYEE_NAME,
            amount=txn.amount,
            currency=txn.currency,
            txn_note=f"SaaS Ref {reference}",
        )
        return _build_qr_image_bytes(upi_payload)

    def submit_utr(
        self,
        tenant_id: int,
        reference: str,
        utr: str,
        payer_vpa: Optional[str],
        proof_image_url: Optional[str],
    ) -> SaaSUPITransaction:
        """
        Transitions a pending transaction to submitted after UTR entry.

        Rules:
        - Transaction must be in 'pending' state.
        - UTR must be non-empty (enforced at schema level, double-checked here).
        - UTR must not already exist in submitted/verified transactions.
        - Tenant isolation is enforced.
        """
        utr = utr.strip()
        if not utr:
            raise AppException("UTR cannot be empty")

        txn = self._get_txn_for_tenant(tenant_id, reference)

        if txn.status != PENDING:
            raise AppException(
                f"Transaction is in '{txn.status}' state and cannot accept UTR submission. "
                "Only 'pending' transactions can be submitted."
            )

        # Duplicate UTR check — across submitted and verified states only
        # Rejected records are historical and their UTR slot is reclaimed
        duplicate = (
            self.db.query(SaaSUPITransaction)
            .filter(
                SaaSUPITransaction.utr == utr,
                SaaSUPITransaction.status.in_([SUBMITTED, VERIFIED]),
            )
            .first()
        )
        if duplicate:
            raise ConflictException(
                f"UTR '{utr}' has already been used for reference '{duplicate.reference}'. "
                "Each UTR may only pay one invoice."
            )

        txn.utr = utr
        txn.status = SUBMITTED
        txn.submitted_at = datetime.utcnow()
        if payer_vpa:
            txn.payer_vpa = payer_vpa
        if proof_image_url:
            txn.proof_image_url = proof_image_url

        self.db.commit()
        self.db.refresh(txn)
        return txn

    def get_transaction(self, tenant_id: int, reference: str) -> SaaSUPITransaction:
        """Retrieves a tenant-isolated transaction by reference."""
        return self._get_txn_for_tenant(tenant_id, reference)

    # ------------------------------------------------------------------
    # Super Admin-facing
    # ------------------------------------------------------------------

    def list_transactions_admin(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        reference: Optional[str] = None,
        utr: Optional[str] = None,
        tenant_id: Optional[int] = None,
    ) -> dict:
        """
        Paginated list of all UPI transactions across tenants.
        Super Admin access only.
        """
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        query = self.db.query(SaaSUPITransaction)

        if status:
            query = query.filter(SaaSUPITransaction.status == status.strip().lower())
        if reference:
            query = query.filter(SaaSUPITransaction.reference == reference.strip())
        if utr:
            query = query.filter(SaaSUPITransaction.utr == utr.strip())
        if tenant_id is not None:
            query = query.filter(SaaSUPITransaction.tenant_id == tenant_id)

        total = query.count()
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        skip = (page - 1) * page_size

        items = (
            query
            .order_by(
                SaaSUPITransaction.created_at.desc(),
                SaaSUPITransaction.id.desc(),
            )
            .offset(skip)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_transaction_admin(self, reference: str) -> SaaSUPITransaction:
        """Retrieves any transaction by reference — no tenant isolation (Super Admin)."""
        txn = (
            self.db.query(SaaSUPITransaction)
            .filter(SaaSUPITransaction.reference == reference)
            .first()
        )
        if not txn:
            raise NotFoundException(f"UPI transaction '{reference}' not found")
        return txn

    def verify_transaction(
        self,
        reference: str,
        super_admin_id: int,
    ) -> SaaSUPITransaction:
        """
        Atomically verifies a submitted UPI transaction.

        Transaction boundary:
          1. Lock SaaSUPITransaction FOR UPDATE (prevents concurrent double-verify)
          2. Assert status == 'submitted'
          3. Validate subscription is in a verifiable state (trialing | past_due)
          4. Lock SaaSInvoice FOR UPDATE
          5. Lock SaaSSubscription FOR UPDATE
          6. Lock Tenant FOR UPDATE
          7. Mutate:
             - txn.status = verified, txn.verified_at = now, txn.verified_by_super_admin_id = sa_id
             - invoice.status = paid, invoice.paid_at = now
             - subscription.status = active
             - sync_tenant_projection()
          8. Commit once

        If any step fails, the entire transaction rolls back.
        """
        from app.models.tenant import Tenant

        # 1. Lock UPI transaction
        txn = (
            self.db.query(SaaSUPITransaction)
            .filter(SaaSUPITransaction.reference == reference)
            .with_for_update()
            .first()
        )
        if not txn:
            raise NotFoundException(f"UPI transaction '{reference}' not found")

        # 2. Assert state
        if txn.status == VERIFIED:
            raise ConflictException(
                f"Transaction '{reference}' is already verified. "
                "Concurrent verification detected."
            )
        if txn.status != SUBMITTED:
            raise AppException(
                f"Transaction '{reference}' is in '{txn.status}' state. "
                "Only 'submitted' transactions can be verified."
            )

        # 3. Lock and validate subscription
        subscription = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.id == txn.subscription_id)
            .with_for_update()
            .first()
        )
        if not subscription:
            raise NotFoundException(f"Subscription {txn.subscription_id} not found")

        if subscription.status in TERMINAL_SUBSCRIPTION_STATUSES:
            raise AppException(
                f"Cannot verify payment for a '{subscription.status}' subscription. "
                "Terminal subscriptions cannot be reactivated via payment verification."
            )
        if subscription.status not in VERIFIABLE_SUBSCRIPTION_STATUSES:
            raise AppException(
                f"Subscription status '{subscription.status}' does not support payment verification. "
                f"Allowed: {VERIFIABLE_SUBSCRIPTION_STATUSES}"
            )

        # 4. Lock invoice
        invoice = (
            self.db.query(SaaSInvoice)
            .filter(SaaSInvoice.id == txn.invoice_id)
            .with_for_update()
            .first()
        )
        if not invoice:
            raise NotFoundException(f"Invoice {txn.invoice_id} not found")

        # 5. Lock tenant
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == txn.tenant_id)
            .with_for_update()
            .first()
        )
        if not tenant:
            raise NotFoundException(f"Tenant {txn.tenant_id} not found")

        now = datetime.utcnow()

        # 6. Apply state transitions atomically
        rows_updated = (
            self.db.query(SaaSUPITransaction)
            .filter(
                SaaSUPITransaction.id == txn.id,
                SaaSUPITransaction.status == SUBMITTED,
            )
            .update(
                {
                    SaaSUPITransaction.status: VERIFIED,
                    SaaSUPITransaction.verified_at: now,
                    SaaSUPITransaction.verified_by_super_admin_id: super_admin_id,
                },
                synchronize_session="fetch",
            )
        )
        if rows_updated == 0:
            raise ConflictException(
                f"Transaction '{reference}' is already verified. "
                "Concurrent verification detected."
            )

        invoice.status = "paid"
        invoice.paid_at = now

        # For renewal cycles, advance period continuously from old current_period_end
        if invoice.billing_reason == "subscription_cycle":
            old_period_end = subscription.current_period_end
            subscription.current_period_start = old_period_end
            if subscription.billing_interval.strip().lower() == "yearly":
                subscription.current_period_end = old_period_end + relativedelta(years=1)
            else:
                subscription.current_period_end = old_period_end + relativedelta(months=1)
        elif invoice.billing_reason == "plan_upgrade":
            if not subscription.pending_plan_id:
                raise AppException(
                    f"Subscription {subscription.id} has no pending plan change for upgrade invoice {invoice.id}"
                )
            from app.models.saas_billing import SaaSPlan
            target_plan = (
                self.db.query(SaaSPlan)
                .filter(SaaSPlan.id == subscription.pending_plan_id)
                .first()
            )
            if not target_plan:
                raise NotFoundException(
                    f"Target SaaS Plan {subscription.pending_plan_id} not found"
                )
            if not target_plan.is_active:
                raise AppException(
                    f"Target SaaS Plan '{target_plan.name}' is inactive"
                )

            # Apply plan upgrade
            subscription.plan_id = target_plan.id
            subscription.unit_price = target_plan.price
            subscription.billing_interval = target_plan.billing_interval
            subscription.currency = target_plan.currency
            subscription.pending_plan_id = None

        subscription.status = "active"

        # 7. Sync legacy tenant projection and authoritative pointer
        tenant.current_subscription_id = subscription.id
        svc = SaaSSubscriptionService(self.db)
        svc.sync_tenant_projection(subscription)

        # 8. Single commit
        self.db.commit()
        self.db.refresh(txn)
        return txn

    def reject_transaction(
        self,
        reference: str,
        super_admin_id: int,
        rejection_reason: str,
    ) -> SaaSUPITransaction:
        """
        Atomically rejects a submitted UPI transaction.

        - Only 'submitted' transactions can be rejected.
        - Invoice remains 'unpaid'; subscription is unchanged.
        - The rejected record is preserved as a historical record.
        - A new checkout reference is required for retry.
        """
        txn = (
            self.db.query(SaaSUPITransaction)
            .filter(SaaSUPITransaction.reference == reference)
            .with_for_update()
            .first()
        )
        if not txn:
            raise NotFoundException(f"UPI transaction '{reference}' not found")

        if txn.status == REJECTED:
            raise ConflictException(
                f"Transaction '{reference}' is already rejected."
            )
        if txn.status != SUBMITTED:
            raise AppException(
                f"Transaction '{reference}' is in '{txn.status}' state. "
                "Only 'submitted' transactions can be rejected."
            )

        rows_updated = (
            self.db.query(SaaSUPITransaction)
            .filter(
                SaaSUPITransaction.id == txn.id,
                SaaSUPITransaction.status == SUBMITTED,
            )
            .update(
                {
                    SaaSUPITransaction.status: REJECTED,
                    SaaSUPITransaction.rejection_reason: rejection_reason,
                    SaaSUPITransaction.verified_by_super_admin_id: super_admin_id,
                },
                synchronize_session="fetch",
            )
        )
        if rows_updated == 0:
            raise ConflictException(
                f"Transaction '{reference}' is already processed."
            )

        # Invoice remains unpaid; subscription unchanged
        self.db.commit()
        self.db.refresh(txn)
        return txn

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_payable_invoice(self, tenant_id: int) -> SaaSInvoice:
        """
        Returns the most recent unpaid invoice for a tenant.
        Raises NotFoundException if none exists.
        """
        invoice = (
            self.db.query(SaaSInvoice)
            .filter(
                SaaSInvoice.tenant_id == tenant_id,
                SaaSInvoice.status.in_(PAYABLE_INVOICE_STATUSES),
            )
            .order_by(
                SaaSInvoice.due_date.asc(),
                SaaSInvoice.id.asc(),
            )
            .first()
        )
        if not invoice:
            raise NotFoundException(
                "No payable invoice found for this tenant. "
                "All invoices may already be paid or none have been generated yet."
            )
        return invoice

    def _get_subscription(self, subscription_id: int, tenant_id: int) -> SaaSSubscription:
        """Returns a subscription owned by the tenant. Raises NotFoundException otherwise."""
        sub = (
            self.db.query(SaaSSubscription)
            .filter(
                SaaSSubscription.id == subscription_id,
                SaaSSubscription.tenant_id == tenant_id,
            )
            .first()
        )
        if not sub:
            raise NotFoundException(
                f"Subscription {subscription_id} not found for tenant {tenant_id}"
            )
        return sub

    def _get_txn_for_tenant(self, tenant_id: int, reference: str) -> SaaSUPITransaction:
        """
        Retrieves a UPI transaction enforcing tenant isolation.
        Returns 404 if the transaction does not exist or belongs to another tenant.
        """
        txn = (
            self.db.query(SaaSUPITransaction)
            .filter(
                SaaSUPITransaction.reference == reference,
                SaaSUPITransaction.tenant_id == tenant_id,
            )
            .first()
        )
        if not txn:
            raise NotFoundException(f"UPI transaction '{reference}' not found")
        return txn
