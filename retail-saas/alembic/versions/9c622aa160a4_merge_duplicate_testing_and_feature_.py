"""merge duplicate testing and feature merge revisions

Revision ID: 9c622aa160a4
Revises: c77cf5d6d3c2, 27db81965787
Create Date: 2026-10-14 18:48:44.251725

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c622aa160a4'
down_revision: Union[str, None] = ('c77cf5d6d3c2', '27db81965787')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
