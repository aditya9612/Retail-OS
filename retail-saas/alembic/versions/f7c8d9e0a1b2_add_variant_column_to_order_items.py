"""add variant column to order_items

Revision ID: f7c8d9e0a1b2
Revises: e9b2d4f6a8c0
Create Date: 2026-11-27 11:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "f7c8d9e0a1b2"
down_revision: Union[str, None] = "e9b2d4f6a8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "order_items" not in tables:
        return

    cols = {c["name"] for c in inspector.get_columns("order_items")}
    if "variant" not in cols:
        op.add_column(
            "order_items",
            sa.Column("variant", sa.String(length=100), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "order_items" not in tables:
        return

    cols = {c["name"] for c in inspector.get_columns("order_items")}
    if "variant" in cols:
        op.drop_column("order_items", "variant")
