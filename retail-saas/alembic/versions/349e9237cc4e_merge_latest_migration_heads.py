"""merge latest migration heads

Revision ID: 349e9237cc4e
Revises: 9b365462e602, bc7a49751a24
Create Date: 2026-08-13 16:37:28.800471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '349e9237cc4e'
down_revision: Union[str, None] = ('9b365462e602', 'bc7a49751a24')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
