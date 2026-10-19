"""merge super admin PIN and invoice return tracking heads

Revision ID: c77cf5d6d3c2
Revises: 83791b05deb5, b2c3d4e5f6a7
Create Date: 2026-10-14 12:37:27.845728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c77cf5d6d3c2'
down_revision: Union[str, None] = ('83791b05deb5', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
