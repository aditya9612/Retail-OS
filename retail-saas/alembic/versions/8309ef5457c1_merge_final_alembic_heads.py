"""Merge final Alembic heads

Revision ID: 8309ef5457c1
Revises: 201eae22f055, bc131c6e1e4d
Create Date: 2026-08-19 11:46:26.670321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8309ef5457c1'
down_revision: Union[str, None] = ('201eae22f055', 'bc131c6e1e4d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
