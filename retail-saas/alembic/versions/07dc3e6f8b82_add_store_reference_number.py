"""add_store_reference_number

Revision ID: 07dc3e6f8b82
Revises: 457c22ac5811
Create Date: 2026-11-05 17:34:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07dc3e6f8b82'
down_revision: Union[str, None] = '457c22ac5811'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "stores" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("stores")}
        if "reference_number" not in existing_cols:
            with op.batch_alter_table("stores", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("reference_number", sa.String(100), nullable=True)
                )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "stores" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("stores")}
        if "reference_number" in existing_cols:
            with op.batch_alter_table("stores", schema=None) as batch_op:
                batch_op.drop_column("reference_number")
