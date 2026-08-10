"""merge multiple heads

Revision ID: c03612560a14
Revises: 8c04e1551529, a1b2c3d4e5f6, f520870f4226
Create Date: 2026-07-29 16:10:17.996068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c03612560a14'
down_revision: Union[str, None] = ('8c04e1551529', 'a1b2c3d4e5f6', 'f520870f4226')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
