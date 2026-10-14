"""merge testing and feature heads

Revision ID: 27db81965787
Revises: 83791b05deb5, b2c3d4e5f6a7
Create Date: 2026-10-14 18:16:04.410505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27db81965787'
down_revision: Union[str, None] = ('83791b05deb5', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
