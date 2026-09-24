"""merge current alembic heads

Revision ID: a92528f55a80
Revises: 2440a629015a, 6e5d4c3b2a1f, de85aafb4c05
Create Date: 2026-09-23 10:15:50.041145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a92528f55a80'
down_revision: Union[str, None] = ('2440a629015a', '6e5d4c3b2a1f', 'de85aafb4c05')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
