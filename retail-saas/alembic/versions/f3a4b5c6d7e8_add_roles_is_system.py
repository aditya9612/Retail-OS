"""add is_system to roles if missing

Revision ID: f3a4b5c6d7e8
Revises: 06b_add_order_items_variant_id
Create Date: 2026-10-06 18:55:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'f3a4b5c6d7e8'
down_revision = '06b_add_order_items_variant_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "roles" in tables:
        columns = {c["name"] for c in inspector.get_columns("roles")}
        if "is_system" not in columns:
            op.add_column(
                "roles",
                sa.Column("is_system", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "roles" in tables:
        columns = {c["name"] for c in inspector.get_columns("roles")}
        if "is_system" in columns:
            op.drop_column("roles", "is_system")
