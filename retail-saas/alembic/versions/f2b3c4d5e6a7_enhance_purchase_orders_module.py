"""enhance purchase orders module with warehouse_id, taxation, workflow and audit trail

Revision ID: f2b3c4d5e6a7
Revises: e9a1b2c3d4e5
Create Date: 2026-10-19 17:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b3c4d5e6a7'
down_revision: Union[str, None] = 'e9a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    po_columns = [c["name"] for c in inspector.get_columns("purchase_orders")]
    po_item_columns = [c["name"] for c in inspector.get_columns("purchase_order_items")]

    # 1. Update purchase_orders table
    if "warehouse_id" not in po_columns:
        op.add_column("purchase_orders", sa.Column("warehouse_id", sa.Integer(), nullable=True))
        try:
            op.create_index("ix_purchase_orders_warehouse_id", "purchase_orders", ["warehouse_id"])
        except Exception:
            pass
        try:
            op.create_foreign_key("fk_purchase_orders_warehouse_id", "purchase_orders", "warehouses", ["warehouse_id"], ["id"])
        except Exception:
            pass

    if "created_by_id" not in po_columns:
        op.add_column("purchase_orders", sa.Column("created_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_purchase_orders_created_by_id", "purchase_orders", "users", ["created_by_id"], ["id"])
        except Exception:
            pass

    if "approved_by_id" not in po_columns:
        op.add_column("purchase_orders", sa.Column("approved_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_purchase_orders_approved_by_id", "purchase_orders", "users", ["approved_by_id"], ["id"])
        except Exception:
            pass

    if "approved_at" not in po_columns:
        op.add_column("purchase_orders", sa.Column("approved_at", sa.DateTime(), nullable=True))

    if "cancelled_at" not in po_columns:
        op.add_column("purchase_orders", sa.Column("cancelled_at", sa.DateTime(), nullable=True))

    if "cancellation_reason" not in po_columns:
        op.add_column("purchase_orders", sa.Column("cancellation_reason", sa.Text(), nullable=True))

    if "subtotal" not in po_columns:
        op.add_column("purchase_orders", sa.Column("subtotal", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False))

    if "tax_amount" not in po_columns:
        op.add_column("purchase_orders", sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False))

    if "discount_amount" not in po_columns:
        op.add_column("purchase_orders", sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False))

    if "shipping_charges" not in po_columns:
        op.add_column("purchase_orders", sa.Column("shipping_charges", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False))

    if "is_deleted" not in po_columns:
        op.add_column("purchase_orders", sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("0"), nullable=False))

    # 2. Update purchase_order_items table
    if "tax_rate" not in po_item_columns:
        op.add_column("purchase_order_items", sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), server_default="0.00", nullable=False))

    if "tax_amount" not in po_item_columns:
        op.add_column("purchase_order_items", sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), server_default="0.00", nullable=False))

    if "hsn_code" not in po_item_columns:
        op.add_column("purchase_order_items", sa.Column("hsn_code", sa.String(length=50), nullable=True))

    if "unit_of_measure" not in po_item_columns:
        op.add_column("purchase_order_items", sa.Column("unit_of_measure", sa.String(length=30), server_default="pcs", nullable=True))


def downgrade() -> None:
    pass

