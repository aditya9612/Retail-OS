"""add email, is_main, and address fields to stores if missing

Revision ID: c6d7e8f9a0b1
Revises: a4b5c6d7e8f9
Create Date: 2026-10-06 19:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'c6d7e8f9a0b1'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "stores" in tables:
        columns = {c["name"] for c in inspector.get_columns("stores")}
        if "email" not in columns:
            op.add_column(
                "stores",
                sa.Column("email", sa.String(255), nullable=True),
            )
        if "is_main" not in columns:
            op.add_column(
                "stores",
                sa.Column("is_main", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            )
        if "code" not in columns:
            op.add_column(
                "stores",
                sa.Column("code", sa.String(50), nullable=True),
            )
        if "city" not in columns:
            op.add_column(
                "stores",
                sa.Column("city", sa.String(100), nullable=True),
            )
        if "state" not in columns:
            op.add_column(
                "stores",
                sa.Column("state", sa.String(100), nullable=True),
            )
        if "pincode" not in columns:
            op.add_column(
                "stores",
                sa.Column("pincode", sa.String(20), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "stores" in tables:
        columns = {c["name"] for c in inspector.get_columns("stores")}
        if "email" in columns:
            op.drop_column("stores", "email")
