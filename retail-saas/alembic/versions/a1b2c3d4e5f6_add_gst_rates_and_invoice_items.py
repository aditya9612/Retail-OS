"""Add gst_rates and invoice_items tables for Billing & GST module."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "cd06817f943b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gst_rates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("hsn_code", sa.String(length=20), nullable=False),
        sa.Column("gst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("cgst", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("sgst", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("igst", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("status", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "hsn_code", name="uq_gst_rates_tenant_hsn"),
    )
    op.create_index("ix_gst_rates_tenant_id", "gst_rates", ["tenant_id"])
    op.create_index("ix_gst_rates_hsn_code", "gst_rates", ["hsn_code"])

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("gst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("gst_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_items_invoice_id", table_name="invoice_items")
    op.drop_table("invoice_items")
    op.drop_index("ix_gst_rates_hsn_code", table_name="gst_rates")
    op.drop_index("ix_gst_rates_tenant_id", table_name="gst_rates")
    op.drop_table("gst_rates")
