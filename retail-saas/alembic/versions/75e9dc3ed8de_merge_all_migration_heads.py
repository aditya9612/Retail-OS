"""merge all migration heads

Revision ID: 75e9dc3ed8de
Revises: 569dd1563f23, 9b365462e602, bc7a49751a24
Create Date: 2026-08-13 17:38:41.016698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75e9dc3ed8de'
down_revision: Union[str, None] = ('569dd1563f23', '9b365462e602', 'bc7a49751a24')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
