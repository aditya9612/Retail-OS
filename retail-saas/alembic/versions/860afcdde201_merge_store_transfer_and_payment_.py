"""merge store transfer and payment migration heads

Revision ID: 860afcdde201
Revises: 854293ecc656, a990c210e4f2
Create Date: 2026-09-11 18:33:18.463470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '860afcdde201'
down_revision: Union[str, None] = ('854293ecc656', 'a990c210e4f2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
