"""merge POS product batch and inventory expiry heads

Revision ID: ec6c05c7077c
Revises: aff441ad6053, c3d4e5f6a7b8
Create Date: 2026-10-06 11:45:30.540086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec6c05c7077c'
down_revision: Union[str, None] = ('aff441ad6053', 'c3d4e5f6a7b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
