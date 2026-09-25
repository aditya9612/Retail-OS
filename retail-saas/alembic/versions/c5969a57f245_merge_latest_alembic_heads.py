"""merge latest alembic heads

Revision ID: c5969a57f245
Revises: 9599f1c1ddd1, c070896d644a
Create Date: 2026-09-24 18:37:26.265164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5969a57f245'
down_revision: Union[str, None] = ('9599f1c1ddd1', 'c070896d644a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
