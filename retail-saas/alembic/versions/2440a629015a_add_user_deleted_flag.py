"""Add user deleted flag

Revision ID: 2440a629015a
Revises: a8217dfae6d5
Create Date: 2026-09-21 15:37:17.612440

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2440a629015a"
down_revision: Union[str, None] = "a8217dfae6d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_users_is_deleted",
        "users",
        ["is_deleted"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_is_deleted", table_name="users")
    op.drop_column("users", "is_deleted")
