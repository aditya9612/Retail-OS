"""Merge multiple heads

Revision ID: 1f386b6d9d12
Revises: 8c04e1551529, f1a2b3c4d5e6, f520870f4226
Create Date: 2026-07-24 13:33:13.852821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f386b6d9d12'
down_revision: Union[str, None] = ('8c04e1551529', 'f1a2b3c4d5e6', 'f520870f4226')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
