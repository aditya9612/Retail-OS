"""merge testing product price and saas billing heads

Revision ID: b74a887c60d8
Revises: c070896d644a, d1e2f3a4b5c6
Create Date: 2026-09-24 10:13:25.098404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b74a887c60d8'
down_revision: Union[str, None] = ('c070896d644a', 'd1e2f3a4b5c6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
