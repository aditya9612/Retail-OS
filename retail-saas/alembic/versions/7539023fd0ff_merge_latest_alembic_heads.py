"""merge latest alembic heads

Revision ID: 7539023fd0ff
Revises: 660ae3fea3b6, 81f09a280edf
Create Date: 2026-08-31 16:29:41.826326

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7539023fd0ff'
down_revision: Union[str, None] = ('660ae3fea3b6', '81f09a280edf')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
