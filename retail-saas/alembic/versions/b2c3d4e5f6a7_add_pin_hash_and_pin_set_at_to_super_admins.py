"""Add pin_hash and pin_set_at columns to super_admins table

Revision ID: b2c3d4e5f6a7
Revises: ce72800aa56b
Create Date: 2026-10-13 19:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "ce72800aa56b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "super_admins" in tables:
        cols = {c["name"] for c in inspector.get_columns("super_admins")}
        if "pin_hash" not in cols:
            op.add_column(
                "super_admins",
                sa.Column("pin_hash", sa.String(255), nullable=True),
            )
        if "pin_set_at" not in cols:
            op.add_column(
                "super_admins",
                sa.Column("pin_set_at", sa.DateTime(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "super_admins" in tables:
        cols = {c["name"] for c in inspector.get_columns("super_admins")}
        if "pin_set_at" in cols:
            op.drop_column("super_admins", "pin_set_at")
        if "pin_hash" in cols:
            op.drop_column("super_admins", "pin_hash")

