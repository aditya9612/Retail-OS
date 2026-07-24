"""Merge three heads

Revision ID: 75d06fba5b2e
Revises: 8c04e1551529, a1b2c3d4e5f6, f520870f4226
Create Date: 2026-07-16 16:34:33.383602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75d06fba5b2e'
down_revision: Union[str, None] = ('8c04e1551529', 'a1b2c3d4e5f6', 'f520870f4226')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
