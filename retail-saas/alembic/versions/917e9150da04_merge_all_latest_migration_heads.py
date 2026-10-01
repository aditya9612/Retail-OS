"""Merge all latest migration heads

Revision ID: 917e9150da04
Revises: 412e696d6f93, ec215d5db1fa
Create Date: 2026-09-29 19:40:07.191908

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '917e9150da04'
down_revision: Union[str, None] = ('412e696d6f93', 'ec215d5db1fa')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
