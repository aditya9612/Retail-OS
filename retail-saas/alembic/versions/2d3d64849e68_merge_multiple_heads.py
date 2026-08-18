"""merge multiple heads

Revision ID: 2d3d64849e68
Revises: 1365f19c2490, 75e9dc3ed8de
Create Date: 2026-08-18 13:18:51.368553

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d3d64849e68'
down_revision: Union[str, None] = ('1365f19c2490', '75e9dc3ed8de')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
