from datetime import datetime
from decimal import Decimal
import math
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
)
from app.models.saas_billing import (
    SaaSInvoice,
    SaaSInvoiceSequence,
    SaaSSubscription,
)
from app.models.tenant import Tenant


ALLOWED_BILLING_REASONS = [
    "trial_conversion",
    "subscription_cycle",
    "plan_upgrade",
    "manual_renewal",
]

INVOICEABLE_STATUSES = ["trialing", "active", "past_due"]


class SaaSInvoiceService:
    def __init__(self, db: Session):
        self.db = db

    def generate_invoice_number(self, year: int) -> str:
        """
        Atomically generates the next invoice number in the format INV-SAAS-{YYYY}-{00000}.
        Uses pessimistic row-locking on saas_invoice_sequences to prevent race conditions.
        """
        seq_row = (
            self.db.query(SaaSInvoiceSequence)
            .filter(SaaSInvoiceSequence.year == year)
            .with_for_update()
            .first()
        )

        if not seq_row:
            try:
                # Attempt to initialize sequence record for the year using a savepoint
                with self.db.begin_nested():
                    seq_row = SaaSInvoiceSequence(year=year, last_sequence=0)
                    self.db.add(seq_row)
                    self.db.flush()
            except IntegrityError:
                # Concurrent transaction created the row; query with row lock
                seq_row = (
                    self.db.query(SaaSInvoiceSequence)
                    .filter(SaaSInvoiceSequence.year == year)
                    .with_for_update()
                    .one()
                )

        seq_row.last_sequence += 1
        self.db.flush()

        return f"INV-SAAS-{year}-{seq_row.last_sequence:05d}"

    def create_invoice(
        self,
        subscription_id: int,
        billing_reason: str = "subscription_cycle",
        due_date: Optional[datetime] = None,
        notes: Optional[str] = None,
        idempotent: bool = True,
    ) -> SaaSInvoice:
        """
        Creates a SaaS invoice from an authoritative subscription within the caller's transaction.
        - Derives tenant_id, subtotal, and currency strictly from the SaaSSubscription snapshot.
        - Defers GST: tax_amount = Decimal("0.00"), total_amount = subtotal.
        - Sets initial status to 'unpaid' and paid_at = None.
        - Sets due_date to issued timestamp if not specified.
        - Implements idempotency/duplicate protection.
        - Does NOT commit or close the caller's session.
        """
        if billing_reason not in ALLOWED_BILLING_REASONS:
            raise AppException(
                f"Invalid billing reason '{billing_reason}'. Allowed: {ALLOWED_BILLING_REASONS}"
            )

        subscription = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.id == subscription_id)
            .first()
        )
        if not subscription:
            raise NotFoundException(
                f"SaaSSubscription with id {subscription_id} not found"
            )

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == subscription.tenant_id)
            .first()
        )
        if not tenant:
            raise NotFoundException(
                f"Tenant {subscription.tenant_id} not found"
            )

        if subscription.status not in INVOICEABLE_STATUSES:
            raise AppException(
                f"Cannot generate invoice for subscription in '{subscription.status}' status"
            )

        # Idempotency / Duplicate Check
        existing_unpaid = (
            self.db.query(SaaSInvoice)
            .filter(
                SaaSInvoice.subscription_id == subscription.id,
                SaaSInvoice.billing_reason == billing_reason,
                SaaSInvoice.status == "unpaid",
            )
            .first()
        )
        if existing_unpaid:
            if idempotent:
                return existing_unpaid
            raise ConflictException(
                f"An unpaid invoice already exists for subscription {subscription_id} and reason '{billing_reason}'"
            )

        # Monetary calculation from subscription snapshot
        subtotal = subscription.unit_price
        tax_amount = Decimal("0.00")
        total_amount = subtotal + tax_amount

        invoice_due_date = due_date or datetime.utcnow()
        invoice_number = self.generate_invoice_number(invoice_due_date.year)

        invoice = SaaSInvoice(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            invoice_number=invoice_number,
            billing_reason=billing_reason,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency=subscription.currency,
            status="unpaid",
            due_date=invoice_due_date,
            paid_at=None,
            pdf_url=None,
            notes=notes,
        )

        try:
            with self.db.begin_nested():
                self.db.add(invoice)
                self.db.flush()
        except IntegrityError:
            # Fallback if invoice number collided unexpectedly; safely retry sequence generation once
            invoice.invoice_number = self.generate_invoice_number(invoice_due_date.year)
            self.db.add(invoice)
            self.db.flush()

        return invoice

    def get_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
    ) -> SaaSInvoice:
        """
        Retrieves a single SaaS invoice strictly enforcing tenant isolation.
        Returns 404 if not found or if belonging to another tenant (zero cross-tenant leak).
        """
        invoice = (
            self.db.query(SaaSInvoice)
            .filter(
                SaaSInvoice.id == invoice_id,
                SaaSInvoice.tenant_id == tenant_id,
            )
            .first()
        )
        if not invoice:
            raise NotFoundException("Invoice not found")

        return invoice

    def list_billing_history(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        Lists paginated SaaS invoices for a tenant.
        Enforces tenant isolation and deterministic ordering (created_at DESC, id DESC).
        """
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        query = self.db.query(SaaSInvoice).filter(
            SaaSInvoice.tenant_id == tenant_id
        )

        total = query.count()
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        skip = (page - 1) * page_size

        items = (
            query
            .order_by(
                SaaSInvoice.created_at.desc(),
                SaaSInvoice.id.desc(),
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
