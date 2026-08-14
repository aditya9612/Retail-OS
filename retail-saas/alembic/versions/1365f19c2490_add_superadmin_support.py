"""add superadmin support

Revision ID: 1365f19c2490
Revises: eb1d473977a5
Create Date: 2026-08-13 20:04:55.260086
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "1365f19c2490"
down_revision: Union[str, None] = "eb1d473977a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow SuperAdmin to exist without a tenant.
    op.alter_column(
        "roles",
        "tenant_id",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )

    op.alter_column(
        "users",
        "tenant_id",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )


def downgrade() -> None:
    # Restore tenant_id as NOT NULL.
    op.alter_column(
        "users",
        "tenant_id",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )

    op.alter_column(
        "roles",
        "tenant_id",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )