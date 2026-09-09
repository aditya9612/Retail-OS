"""Register existing store transfers tables

Revision ID: 5cb271a7a4ee
Revises: 6cffa3e2dd40
"""

from typing import Sequence, Union


revision: str = "5cb271a7a4ee"
down_revision: Union[str, None] = "6cffa3e2dd40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # store_transfers and store_transfer_items already exist
    # in the database. This migration only registers them.
    pass


def downgrade() -> None:
    pass
