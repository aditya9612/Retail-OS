"""Drop legacy global invoice unique constraint and repair historical invoice status.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-09 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "invoices" in tables:
        indexes = {i["name"]: i for i in inspector.get_indexes("invoices")}
        uqs = {uq["name"]: uq for uq in inspector.get_unique_constraints("invoices")}

        # 1. Drop legacy global unique constraint/index on invoice_number
        if "invoice_number" in indexes and indexes["invoice_number"]["unique"]:
            op.drop_index("invoice_number", table_name="invoices")
        elif "invoice_number" in uqs:
            op.drop_constraint("invoice_number", "invoices", type_="unique")

        # 2. Ensure non-unique performance index on invoice_number exists
        indexes = {i["name"]: i for i in inspector.get_indexes("invoices")}
        if "ix_invoices_invoice_number" not in indexes:
            op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"], unique=False)

        # 3. Idempotent historical invoice status data repair based on orders & payments lifecycle
        bind.execute(
            sa.text(
                """
                UPDATE invoices
                SET status = CASE
                    WHEN (SELECT status FROM orders WHERE orders.id = invoices.order_id) = 'cancelled' THEN 'cancelled'
                    WHEN (
                        (SELECT COUNT(*) FROM refunds WHERE refunds.invoice_id = invoices.id) > 0
                        OR (SELECT COUNT(*) FROM credit_notes WHERE credit_notes.invoice_id = invoices.id) > 0
                        OR (SELECT status FROM orders WHERE orders.id = invoices.order_id) = 'refunded'
                    ) THEN 'refunded'
                    WHEN (
                        (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payments.order_id = invoices.order_id AND payments.status = 'completed') >= invoices.total_amount
                        OR (SELECT payment_status FROM orders WHERE orders.id = invoices.order_id) = 'paid'
                    ) THEN 'paid'
                    WHEN (
                        (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payments.order_id = invoices.order_id AND payments.status = 'completed') > 0
                    ) THEN 'partially_paid'
                    ELSE 'issued'
                END
                WHERE status = 'issued' OR status IS NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "invoices" in tables:
        indexes = {i["name"]: i for i in inspector.get_indexes("invoices")}
        if "ix_invoices_invoice_number" in indexes:
            op.drop_index("ix_invoices_invoice_number", table_name="invoices")

        if "invoice_number" not in indexes:
            op.create_index("invoice_number", "invoices", ["invoice_number"], unique=True)

