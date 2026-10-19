"""merge invoice and stores inventory heads

Revision ID: 3efc29f3b8e1
Revises: e8f9a0b1c2d3, ee050cec6caf
Create Date: 2026-10-12 18:16:34.436785

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3efc29f3b8e1'
down_revision: Union[str, None] = ('e8f9a0b1c2d3', 'ee050cec6caf')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
