"""add_store_id_and_invoice_number_to_purchase_orders

Revision ID: e4f2a1b3c5d7
Revises: fe39cedfe4f2
Create Date: 2026-10-03 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4f2a1b3c5d7'
down_revision: Union[str, None] = 'fe39cedfe4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("purchase_orders")]

    if "store_id" not in existing_columns:
        op.add_column("purchase_orders", sa.Column("store_id", sa.Integer(), nullable=True))
        op.create_index("ix_purchase_orders_store_id", "purchase_orders", ["store_id"])
        try:
            op.create_foreign_key(
                "fk_purchase_orders_store_id",
                "purchase_orders",
                "stores",
                ["store_id"],
                ["id"],
            )
        except Exception:
            pass

    if "invoice_number" not in existing_columns:
        op.add_column("purchase_orders", sa.Column("invoice_number", sa.String(length=100), nullable=True))
        op.create_index("ix_purchase_orders_invoice_number", "purchase_orders", ["invoice_number"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("purchase_orders")]

    if "invoice_number" in existing_columns:
        try:
            op.drop_index("ix_purchase_orders_invoice_number", table_name="purchase_orders")
        except Exception:
            pass
        op.drop_column("purchase_orders", "invoice_number")

    if "store_id" in existing_columns:
        try:
            op.drop_constraint("fk_purchase_orders_store_id", "purchase_orders", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index("ix_purchase_orders_store_id", table_name="purchase_orders")
        except Exception:
            pass
        op.drop_column("purchase_orders", "store_id")

