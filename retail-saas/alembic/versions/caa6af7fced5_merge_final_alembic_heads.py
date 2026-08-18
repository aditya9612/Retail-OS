"""Merge final Alembic heads

Revision ID: caa6af7fced5
Revises: 2f11224ed364, 75e9dc3ed8de, 9c49eaa4ce9a
Create Date: 2026-08-15 14:31:18.781283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'caa6af7fced5'
down_revision: Union[str, None] = ('2f11224ed364', '75e9dc3ed8de', '9c49eaa4ce9a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
