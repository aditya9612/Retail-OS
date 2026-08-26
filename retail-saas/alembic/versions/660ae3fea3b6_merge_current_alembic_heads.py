"""merge current alembic heads

Revision ID: 660ae3fea3b6
Revises: 201eae22f055, bc131c6e1e4d, e37f24f6ed8e
Create Date: 2026-08-26 16:42:44.540976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '660ae3fea3b6'
down_revision: Union[str, None] = ('201eae22f055', 'bc131c6e1e4d', 'e37f24f6ed8e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
