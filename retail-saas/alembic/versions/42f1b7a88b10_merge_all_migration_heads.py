"""merge all migration heads

Revision ID: 42f1b7a88b10
Revises: 00791fd16996, bc131c6e1e4d
Create Date: 2026-09-04 20:14:51.162872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42f1b7a88b10'
down_revision: Union[str, None] = ('00791fd16996', 'bc131c6e1e4d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
