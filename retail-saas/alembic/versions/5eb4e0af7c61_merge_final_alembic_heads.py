"""Merge final Alembic heads

Revision ID: 5eb4e0af7c61
Revises: 8309ef5457c1, e37f24f6ed8e
Create Date: 2026-08-21 10:56:49.748339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5eb4e0af7c61'
down_revision: Union[str, None] = ('8309ef5457c1', 'e37f24f6ed8e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
