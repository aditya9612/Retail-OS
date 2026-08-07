"""merge heads

Revision ID: 0b82610b941d
Revises: 1f386b6d9d12, 56be81fe89b0, 85d54ffbe4d6
Create Date: 2026-08-07 18:04:23.262714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b82610b941d'
down_revision: Union[str, None] = ('1f386b6d9d12', '56be81fe89b0', '85d54ffbe4d6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
