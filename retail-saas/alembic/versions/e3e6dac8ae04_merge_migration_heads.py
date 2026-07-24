"""merge migration heads

Revision ID: e3e6dac8ae04
Revises: 8c04e1551529, a1b2c3d4e5f6, f520870f4226
Create Date: 2026-07-22 13:00:45.477285

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3e6dac8ae04'
down_revision: Union[str, None] = ('8c04e1551529', 'a1b2c3d4e5f6', 'f520870f4226')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
