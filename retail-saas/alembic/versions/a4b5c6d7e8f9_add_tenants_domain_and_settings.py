"""add domain and settings to tenants if missing

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-10-06 19:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'a4b5c6d7e8f9'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "tenants" in tables:
        columns = {c["name"] for c in inspector.get_columns("tenants")}
        if "slug" in columns and "domain" not in columns:
            if bind.dialect.name == "mysql":
                op.execute(
                    "ALTER TABLE tenants CHANGE COLUMN slug domain VARCHAR(255) NOT NULL"
                )
            else:
                op.alter_column(
                    "tenants",
                    "slug",
                    new_column_name="domain",
                    existing_type=sa.String(255),
                    existing_nullable=False,
                )
        elif "domain" not in columns:
            op.add_column(
                "tenants",
                sa.Column("domain", sa.String(255), nullable=False, server_default=""),
            )

        if "settings" not in columns:
            op.add_column(
                "tenants",
                sa.Column("settings", sa.JSON(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "tenants" in tables:
        columns = {c["name"] for c in inspector.get_columns("tenants")}
        if "settings" in columns:
            op.drop_column("tenants", "settings")
