"""enhance purchase order returns module with return_number, debit_note, workflow, and batch tracking

Revision ID: d9e8f7a6b5c4
Revises: f2b3c4d5e6a7
Create Date: 2026-10-19 18:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e8f7a6b5c4'
down_revision: Union[str, None] = 'f2b3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return_columns = [c["name"] for c in inspector.get_columns("purchase_order_returns")]
    return_item_columns = [c["name"] for c in inspector.get_columns("purchase_order_return_items")]

    # 1. Update purchase_order_returns table
    if "return_number" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("return_number", sa.String(length=100), nullable=True))
        try:
            op.create_index("ix_purchase_order_returns_return_number", "purchase_order_returns", ["return_number"], unique=True)
        except Exception:
            pass

    if "debit_note_number" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("debit_note_number", sa.String(length=100), nullable=True))
        try:
            op.create_index("ix_purchase_order_returns_debit_note_number", "purchase_order_returns", ["debit_note_number"])
        except Exception:
            pass

    if "supplier_id" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("supplier_id", sa.Integer(), nullable=True))
        try:
            op.create_index("ix_purchase_order_returns_supplier_id", "purchase_order_returns", ["supplier_id"])
        except Exception:
            pass
        try:
            op.create_foreign_key("fk_purchase_order_returns_supplier_id", "purchase_order_returns", "suppliers", ["supplier_id"], ["id"])
        except Exception:
            pass

    if "store_id" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("store_id", sa.Integer(), nullable=True))
        try:
            op.create_index("ix_purchase_order_returns_store_id", "purchase_order_returns", ["store_id"])
        except Exception:
            pass
        try:
            op.create_foreign_key("fk_purchase_order_returns_store_id", "purchase_order_returns", "stores", ["store_id"], ["id"])
        except Exception:
            pass

    if "warehouse_id" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("warehouse_id", sa.Integer(), nullable=True))
        try:
            op.create_index("ix_purchase_order_returns_warehouse_id", "purchase_order_returns", ["warehouse_id"])
        except Exception:
            pass
        try:
            op.create_foreign_key("fk_purchase_order_returns_warehouse_id", "purchase_order_returns", "warehouses", ["warehouse_id"], ["id"])
        except Exception:
            pass

    if "created_by_id" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("created_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_purchase_order_returns_created_by_id", "purchase_order_returns", "users", ["created_by_id"], ["id"])
        except Exception:
            pass

    if "approved_by_id" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("approved_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_purchase_order_returns_approved_by_id", "purchase_order_returns", "users", ["approved_by_id"], ["id"])
        except Exception:
            pass

    if "approved_at" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("approved_at", sa.DateTime(), nullable=True))

    if "rejected_by_id" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("rejected_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_purchase_order_returns_rejected_by_id", "purchase_order_returns", "users", ["rejected_by_id"], ["id"])
        except Exception:
            pass

    if "rejected_at" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("rejected_at", sa.DateTime(), nullable=True))

    if "rejection_reason" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("rejection_reason", sa.Text(), nullable=True))

    if "completed_at" not in return_columns:
        op.add_column("purchase_order_returns", sa.Column("completed_at", sa.DateTime(), nullable=True))

    # 2. Update purchase_order_return_items table
    if "batch_number" not in return_item_columns:
        op.add_column("purchase_order_return_items", sa.Column("batch_number", sa.String(length=100), nullable=True))

    if "item_reason" not in return_item_columns:
        op.add_column("purchase_order_return_items", sa.Column("item_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    pass

