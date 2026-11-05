"""add description column to roles table

Revision ID: f4a5b6c7d8e9
Revises: b4c5d6e7f8a9
Create Date: 2026-11-05 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'f4a5b6c7d8e9'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "roles" in tables:
        columns = {c["name"] for c in inspector.get_columns("roles")}
        if "description" not in columns:
            op.add_column(
                "roles",
                sa.Column("description", sa.String(length=255), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "roles" in tables:
        columns = {c["name"] for c in inspector.get_columns("roles")}
        if "description" in columns:
            op.drop_column("roles", "description")

