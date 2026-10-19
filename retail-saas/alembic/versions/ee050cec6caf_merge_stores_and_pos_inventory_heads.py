"""merge stores and POS inventory heads

Revision ID: ee050cec6caf
Revises: c6d7e8f9a0b1, ec6c05c7077c
Create Date: 2026-10-07 10:49:20.697836

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee050cec6caf'
down_revision: Union[str, None] = ('c6d7e8f9a0b1', 'ec6c05c7077c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
