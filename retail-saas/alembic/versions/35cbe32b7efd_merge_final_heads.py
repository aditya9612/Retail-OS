"""Merge final heads

Revision ID: 35cbe32b7efd
Revises: 0b82610b941d, 8b1d37df6083
Create Date: 2026-08-07 19:21:54.698444

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35cbe32b7efd'
down_revision: Union[str, None] = ('0b82610b941d', '8b1d37df6083')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
