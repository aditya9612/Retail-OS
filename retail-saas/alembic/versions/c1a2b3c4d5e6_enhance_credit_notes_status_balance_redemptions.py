"""enhance_credit_notes_status_balance_redemptions

Revision ID: c1a2b3c4d5e6
Revises: d1a2b3c4d5e6
Create Date: 2026-10-23 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3c4d5e6'
down_revision: Union[str, None] = 'd1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "credit_notes" in tables:
        cols = [c["name"] for c in inspector.get_columns("credit_notes")]
        if "status" not in cols:
            op.add_column("credit_notes", sa.Column("status", sa.String(30), nullable=False, server_default="issued"))
        if "balance_amount" not in cols:
            op.add_column("credit_notes", sa.Column("balance_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"))
        if "customer_id" not in cols:
            op.add_column("credit_notes", sa.Column("customer_id", sa.Integer(), nullable=True))
        if "valid_until" not in cols:
            op.add_column("credit_notes", sa.Column("valid_until", sa.DateTime(), nullable=True))
        if "notes" not in cols:
            op.add_column("credit_notes", sa.Column("notes", sa.Text(), nullable=True))

        # Backfill balance_amount = refund_amount where balance_amount is 0.00
        op.execute(
            "UPDATE credit_notes SET balance_amount = refund_amount WHERE balance_amount = 0.00 OR balance_amount IS NULL"
        )

    if "credit_note_redemptions" not in tables:
        op.create_table(
            "credit_note_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("credit_note_id", sa.Integer(), nullable=False),
            sa.Column("invoice_id", sa.Integer(), nullable=True),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("amount_redeemed", sa.Numeric(12, 2), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["credit_note_id"], ["credit_notes.id"]),
            sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        )
        op.create_index("ix_credit_note_redemptions_tenant", "credit_note_redemptions", ["tenant_id"])
        op.create_index("ix_credit_note_redemptions_cn", "credit_note_redemptions", ["credit_note_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "credit_note_redemptions" in tables:
        op.drop_table("credit_note_redemptions")

    if "credit_notes" in tables:
        cols = [c["name"] for c in inspector.get_columns("credit_notes")]
        if "notes" in cols:
            op.drop_column("credit_notes", "notes")
        if "valid_until" in cols:
            op.drop_column("credit_notes", "valid_until")
        if "customer_id" in cols:
            op.drop_column("credit_notes", "customer_id")
        if "balance_amount" in cols:
            op.drop_column("credit_notes", "balance_amount")
        if "status" in cols:
            op.drop_column("credit_notes", "status")

