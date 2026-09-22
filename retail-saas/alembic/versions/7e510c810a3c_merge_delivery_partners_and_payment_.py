"""merge delivery partners and payment heads

Revision ID: 7e510c810a3c
Revises: 6e5d4c3b2a1f, a8217dfae6d5
Create Date: 2026-09-21 15:19:57.585325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e510c810a3c'
down_revision: Union[str, None] = ('6e5d4c3b2a1f', 'a8217dfae6d5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
