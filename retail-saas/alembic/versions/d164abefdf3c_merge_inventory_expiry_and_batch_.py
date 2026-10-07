"""merge_inventory_expiry_and_batch_allocations

Revision ID: d164abefdf3c
Revises: c3d4e5f6a7b8, 06b_order_item_batch_allocations
Create Date: 2026-10-06 13:49:17.922826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd164abefdf3c'
down_revision: Union[str, None] = ('c3d4e5f6a7b8', '06b_order_item_batch_allocations')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
