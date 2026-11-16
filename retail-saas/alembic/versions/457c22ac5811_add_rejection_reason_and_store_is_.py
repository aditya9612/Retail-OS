"""add_rejection_reason_and_store_is_warehouse

Revision ID: 457c22ac5811
Revises: a3b4c5d6e7f8
Create Date: 2026-11-05 15:22:07.168720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '457c22ac5811'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "store_transfers" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("store_transfers")}
        if "rejection_reason" not in existing_cols:
            with op.batch_alter_table("store_transfers", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("rejection_reason", sa.String(500), nullable=True)
                )

    if "stores" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("stores")}
        if "is_warehouse" not in existing_cols:
            with op.batch_alter_table("stores", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("is_warehouse", sa.Boolean(), server_default=sa.text("0"), nullable=False)
                )
        if "reference_number" not in existing_cols:
            with op.batch_alter_table("stores", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("reference_number", sa.String(100), nullable=True)
                )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "store_transfers" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("store_transfers")}
        if "rejection_reason" in existing_cols:
            with op.batch_alter_table("store_transfers", schema=None) as batch_op:
                batch_op.drop_column("rejection_reason")

    if "stores" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("stores")}
        if "reference_number" in existing_cols:
            with op.batch_alter_table("stores", schema=None) as batch_op:
                batch_op.drop_column("reference_number")
        if "is_warehouse" in existing_cols:
            with op.batch_alter_table("stores", schema=None) as batch_op:
                batch_op.drop_column("is_warehouse")
