"""merge latest heads

Revision ID: eb0c7cda81de
Revises: 56be81fe89b0, 85d54ffbe4d6
Create Date: 2026-08-07 18:00:10.410450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb0c7cda81de'
down_revision: Union[str, None] = ('56be81fe89b0', '85d54ffbe4d6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
