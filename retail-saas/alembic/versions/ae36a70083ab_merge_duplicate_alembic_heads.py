"""merge duplicate alembic heads

Revision ID: ae36a70083ab
Revises: 9c622aa160a4, c4c6750a282a
Create Date: 2026-10-15 16:01:35.344304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae36a70083ab'
down_revision: Union[str, None] = ('9c622aa160a4', 'c4c6750a282a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
