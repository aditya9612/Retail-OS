"""merge migration heads

Revision ID: 31de8e306ec3
Revises: 9b365462e602, bc7a49751a24
Create Date: 2026-08-11 18:04:10.533674

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31de8e306ec3'
down_revision: Union[str, None] = ('9b365462e602', 'bc7a49751a24')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
