"""register existing store_targets table

Revision ID: 6cffa3e2dd40
Revises: 42f1b7a88b10
Create Date: 2026-09-08
"""

from typing import Sequence, Union


revision: str = "6cffa3e2dd40"
down_revision: Union[str, None] = "42f1b7a88b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # store_targets already exists in the database.
    # This migration only registers the existing table with Alembic.
    pass


def downgrade() -> None:
    pass