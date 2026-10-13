"""merge return tracking and pos inventory heads

Revision ID: ce72800aa56b
Revises: ee050cec6caf, f1a2b3c4d5e7
Create Date: 2026-10-13 15:50:14.606641

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce72800aa56b'
down_revision: Union[str, None] = ('ee050cec6caf', 'f1a2b3c4d5e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
