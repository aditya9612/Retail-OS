"""Merge final migration heads

Revision ID: 9b365462e602
Revises: 35cbe32b7efd, b47e6d253685
Create Date: 2026-08-10 12:56:52.477494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b365462e602'
down_revision: Union[str, None] = ('35cbe32b7efd', 'b47e6d253685')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
