"""enrich invoice_items with variant and gst snapshot fields

Revision ID: e9b2d4f6a8c0
Revises: f1ebe5f23a40
Create Date: 2026-11-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "e9b2d4f6a8c0"
down_revision: Union[str, None] = "f1ebe5f23a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "invoice_items" not in tables:
        return

    inv_item_cols = {c["name"] for c in inspector.get_columns("invoice_items")}
    inv_item_indexes = {idx["name"] for idx in inspector.get_indexes("invoice_items")}
    inv_item_fks = inspector.get_foreign_keys("invoice_items")
    has_variant_fk = any(
        "variant_id" in fk.get("constrained_columns", [])
        for fk in inv_item_fks
    )

    columns_to_add = [
        ("variant_id", sa.Column("variant_id", sa.Integer(), nullable=True)),
        ("product_name", sa.Column("product_name", sa.String(length=255), nullable=True)),
        ("sku", sa.Column("sku", sa.String(length=100), nullable=True)),
        ("hsn_code", sa.Column("hsn_code", sa.String(length=20), nullable=True)),
        ("unit", sa.Column("unit", sa.String(length=20), nullable=True)),
        (
            "cgst_amount",
            sa.Column(
                "cgst_amount",
                sa.Numeric(precision=10, scale=2),
                nullable=False,
                server_default=sa.text("'0.00'"),
            ),
        ),
        (
            "sgst_amount",
            sa.Column(
                "sgst_amount",
                sa.Numeric(precision=10, scale=2),
                nullable=False,
                server_default=sa.text("'0.00'"),
            ),
        ),
        (
            "igst_amount",
            sa.Column(
                "igst_amount",
                sa.Numeric(precision=10, scale=2),
                nullable=False,
                server_default=sa.text("'0.00'"),
            ),
        ),
    ]

    for col_name, col_def in columns_to_add:
        if col_name not in inv_item_cols:
            op.add_column("invoice_items", col_def)

    # Ensure no NULL tax split rows remain if columns were auto-synced earlier as NULL
    op.execute(sa.text("UPDATE invoice_items SET cgst_amount = 0.00 WHERE cgst_amount IS NULL"))
    op.execute(sa.text("UPDATE invoice_items SET sgst_amount = 0.00 WHERE sgst_amount IS NULL"))
    op.execute(sa.text("UPDATE invoice_items SET igst_amount = 0.00 WHERE igst_amount IS NULL"))

    if "ix_invoice_items_variant_id" not in inv_item_indexes:
        op.create_index(
            "ix_invoice_items_variant_id",
            "invoice_items",
            ["variant_id"],
            unique=False,
        )

    if not has_variant_fk and "product_variants" in tables:
        with op.batch_alter_table("invoice_items", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_invoice_items_variant_id",
                "product_variants",
                ["variant_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "invoice_items" not in tables:
        return

    inv_item_fks = inspector.get_foreign_keys("invoice_items")
    variant_fk_names = [
        fk["name"]
        for fk in inv_item_fks
        if fk.get("name") and "variant_id" in fk.get("constrained_columns", [])
    ]
    if variant_fk_names:
        with op.batch_alter_table("invoice_items", schema=None) as batch_op:
            for fk_name in variant_fk_names:
                batch_op.drop_constraint(fk_name, type_="foreignkey")

    inv_item_indexes = {idx["name"] for idx in inspector.get_indexes("invoice_items")}
    if "ix_invoice_items_variant_id" in inv_item_indexes:
        op.drop_index("ix_invoice_items_variant_id", table_name="invoice_items")

    inv_item_cols = {c["name"] for c in inspector.get_columns("invoice_items")}
    for col_name in (
        "igst_amount",
        "sgst_amount",
        "cgst_amount",
        "unit",
        "hsn_code",
        "sku",
        "product_name",
        "variant_id",
    ):
        if col_name in inv_item_cols:
            op.drop_column("invoice_items", col_name)
