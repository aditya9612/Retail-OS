"""merge latest migration heads

Revision ID: 625d985f22e2
Revises: 2e62fdfe7e4c, 917e9150da04
Create Date: 2026-10-01 20:23:22.464850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '625d985f22e2'
down_revision: Union[str, None] = ('2e62fdfe7e4c', '917e9150da04')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
