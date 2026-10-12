"""Add return tracking columns and invoice item returns canonical table.

Revision ID: f1a2b3c4d5e7
Revises: e8f9a0b1c2d3
Create Date: 2026-10-12 13:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from decimal import Decimal

revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # 1. Add returned_quantity to invoice_items
    if "invoice_items" in tables:
        inv_item_cols = {c["name"] for c in inspector.get_columns("invoice_items")}
        if "returned_quantity" not in inv_item_cols:
            op.add_column(
                "invoice_items",
                sa.Column(
                    "returned_quantity",
                    sa.Numeric(12, 4),
                    nullable=False,
                    server_default=sa.text("'0.0000'"),
                ),
            )

    # 2. Add returned_quantity to order_item_batch_allocations
    if "order_item_batch_allocations" in tables:
        alloc_cols = {c["name"] for c in inspector.get_columns("order_item_batch_allocations")}
        if "returned_quantity" not in alloc_cols:
            op.add_column(
                "order_item_batch_allocations",
                sa.Column(
                    "returned_quantity",
                    sa.Numeric(12, 4),
                    nullable=False,
                    server_default=sa.text("'0.0000'"),
                ),
            )

    # 3. Create canonical invoice_item_returns table
    if "invoice_item_returns" not in tables:
        op.create_table(
            "invoice_item_returns",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False, index=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False, index=True),
            sa.Column("invoice_item_id", sa.BigInteger(), sa.ForeignKey("invoice_items.id"), nullable=False, index=True),
            sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=True, index=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("product_batches.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
            sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("condition", sa.String(30), nullable=False, server_default=sa.text("'sellable'")),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("idempotency_key", sa.String(100), nullable=True, index=True),
            sa.Column("refund_id", sa.Integer(), sa.ForeignKey("refunds.id", ondelete="SET NULL"), nullable=True),
            sa.Column("credit_note_id", sa.Integer(), sa.ForeignKey("credit_notes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_invoice_item_returns_tenant_idemp",
            "invoice_item_returns",
            ["tenant_id", "idempotency_key"],
            unique=True,
        )

    # 4. Add optional return_id to credit_notes
    if "credit_notes" in tables:
        cn_cols = {c["name"] for c in inspector.get_columns("credit_notes")}
        if "return_id" not in cn_cols:
            op.add_column(
                "credit_notes",
                sa.Column(
                    "return_id",
                    sa.BigInteger(),
                    nullable=True,
                ),
            )
            op.create_foreign_key(
                "fk_credit_notes_return_id",
                "credit_notes",
                "invoice_item_returns",
                ["return_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "credit_notes" in tables:
        fks = inspector.get_foreign_keys("credit_notes")
        for fk in fks:
            if "return_id" in fk.get("constrained_columns", []):
                op.drop_constraint(fk["name"], "credit_notes", type_="foreignkey")
        cn_cols = {c["name"] for c in inspector.get_columns("credit_notes")}
        if "return_id" in cn_cols:
            op.drop_column("credit_notes", "return_id")

    if "invoice_item_returns" in tables:
        op.drop_table("invoice_item_returns")

    if "order_item_batch_allocations" in tables:
        alloc_cols = {c["name"] for c in inspector.get_columns("order_item_batch_allocations")}
        if "returned_quantity" in alloc_cols:
            op.drop_column("order_item_batch_allocations", "returned_quantity")

    if "invoice_items" in tables:
        inv_item_cols = {c["name"] for c in inspector.get_columns("invoice_items")}
        if "returned_quantity" in inv_item_cols:
            op.drop_column("invoice_items", "returned_quantity")
