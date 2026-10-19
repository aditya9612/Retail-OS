"""merge duplicate testing and invoice heads

Revision ID: c4c6750a282a
Revises: 27db81965787, c77cf5d6d3c2
Create Date: 2026-10-15 10:23:35.493994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4c6750a282a'
down_revision: Union[str, None] = ('27db81965787', 'c77cf5d6d3c2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
