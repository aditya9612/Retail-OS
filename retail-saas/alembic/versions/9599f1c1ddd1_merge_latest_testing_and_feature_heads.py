"""merge latest testing and feature heads

Revision ID: 9599f1c1ddd1
Revises: 2440a629015a, 7e510c810a3c, de85aafb4c05
Create Date: 2026-09-22 10:10:00.358870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9599f1c1ddd1'
down_revision: Union[str, None] = ('2440a629015a', '7e510c810a3c', 'de85aafb4c05')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
