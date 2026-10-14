"""merge invoice and return tracking heads

Revision ID: 83791b05deb5
Revises: 3efc29f3b8e1, f1a2b3c4d5e7
Create Date: 2026-10-13 12:22:44.139131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83791b05deb5'
down_revision: Union[str, None] = ('3efc29f3b8e1', 'f1a2b3c4d5e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
