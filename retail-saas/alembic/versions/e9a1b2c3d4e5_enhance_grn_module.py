"""enhance grn module with store_id, invoice, logistics, qc, and batch tracking

Revision ID: e9a1b2c3d4e5
Revises: ae36a70083ab
Create Date: 2026-10-19 15:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9a1b2c3d4e5'
down_revision: Union[str, None] = 'ae36a70083ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    grn_columns = [c["name"] for c in inspector.get_columns("grns")]
    grn_item_columns = [c["name"] for c in inspector.get_columns("grn_items")]

    # 1. Update grns table
    if "store_id" not in grn_columns:
        op.add_column("grns", sa.Column("store_id", sa.Integer(), nullable=True))
        try:
            op.create_index("ix_grns_store_id", "grns", ["store_id"])
        except Exception:
            pass
        try:
            op.create_foreign_key("fk_grns_store_id", "grns", "stores", ["store_id"], ["id"])
        except Exception:
            pass

    if "invoice_number" not in grn_columns:
        op.add_column("grns", sa.Column("invoice_number", sa.String(length=100), nullable=True))
        try:
            op.create_index("ix_grns_invoice_number", "grns", ["invoice_number"])
        except Exception:
            pass

    if "invoice_date" not in grn_columns:
        op.add_column("grns", sa.Column("invoice_date", sa.Date(), nullable=True))

    if "vehicle_number" not in grn_columns:
        op.add_column("grns", sa.Column("vehicle_number", sa.String(length=50), nullable=True))

    if "transporter_name" not in grn_columns:
        op.add_column("grns", sa.Column("transporter_name", sa.String(length=100), nullable=True))

    if "rejection_reason" not in grn_columns:
        op.add_column("grns", sa.Column("rejection_reason", sa.Text(), nullable=True))

    if "created_by_id" not in grn_columns:
        op.add_column("grns", sa.Column("created_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_grns_created_by_id", "grns", "users", ["created_by_id"], ["id"])
        except Exception:
            pass

    if "received_by_id" not in grn_columns:
        op.add_column("grns", sa.Column("received_by_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_grns_received_by_id", "grns", "users", ["received_by_id"], ["id"])
        except Exception:
            pass

    # 2. Update grn_items table
    if "accepted_quantity" not in grn_item_columns:
        op.add_column("grn_items", sa.Column("accepted_quantity", sa.Integer(), nullable=True))

    if "rejected_quantity" not in grn_item_columns:
        op.add_column("grn_items", sa.Column("rejected_quantity", sa.Integer(), nullable=True, server_default="0"))

    if "damage_reason" not in grn_item_columns:
        op.add_column("grn_items", sa.Column("damage_reason", sa.String(length=255), nullable=True))

    if "batch_number" not in grn_item_columns:
        op.add_column("grn_items", sa.Column("batch_number", sa.String(length=100), nullable=True))

    if "expiry_date" not in grn_item_columns:
        op.add_column("grn_items", sa.Column("expiry_date", sa.Date(), nullable=True))

    if "unit_cost" not in grn_item_columns:
        op.add_column("grn_items", sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    pass

