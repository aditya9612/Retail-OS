"""Merge employee and warehouse migration heads

Revision ID: 9c49eaa4ce9a
Revises: 569dd1563f23, 5d5148c6eff3
Create Date: 2026-08-14 12:25:36.630489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c49eaa4ce9a'
down_revision: Union[str, None] = ('569dd1563f23', '5d5148c6eff3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
