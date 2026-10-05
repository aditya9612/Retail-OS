"""add_store_targets_and_sales_composite_indexes

Revision ID: f2a3b4c5d6e7
Revises: e4f2a1b3c5d7
Create Date: 2026-10-04 00:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e4f2a1b3c5d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_sales_indexes = [idx["name"] for idx in inspector.get_indexes("sales")]
    if "ix_sales_store_status_created" not in existing_sales_indexes:
        try:
            op.create_index(
                "ix_sales_store_status_created",
                "sales",
                ["store_id", "payment_status", "created_at"],
            )
        except Exception:
            pass

    existing_target_indexes = [idx["name"] for idx in inspector.get_indexes("store_targets")]
    if "ix_store_targets_store_status_dates" not in existing_target_indexes:
        try:
            op.create_index(
                "ix_store_targets_store_status_dates",
                "store_targets",
                ["store_id", "status", "start_date", "end_date"],
            )
        except Exception:
            pass


def downgrade() -> None:
    try:
        op.drop_index("ix_store_targets_store_status_dates", table_name="store_targets")
    except Exception:
        pass
    try:
        op.drop_index("ix_sales_store_status_created", table_name="sales")
    except Exception:
        pass
