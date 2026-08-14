"""merge employee superadmin and wallet heads

Revision ID: 2f11224ed364
Revises: 1365f19c2490, 176cf1381b78, 569dd1563f23
Create Date: 2026-08-14 11:51:50.296625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f11224ed364'
down_revision: Union[str, None] = ('1365f19c2490', '176cf1381b78', '569dd1563f23')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
