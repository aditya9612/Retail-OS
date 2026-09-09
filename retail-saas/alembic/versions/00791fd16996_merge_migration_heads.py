"""merge migration heads

Revision ID: 00791fd16996
Revises: 201eae22f055, e37f24f6ed8e
Create Date: 2026-09-04 20:13:03.584202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00791fd16996'
down_revision: Union[str, None] = ('201eae22f055', 'e37f24f6ed8e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
