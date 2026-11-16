"""merge store and whatsapp migration heads

Revision ID: 05d2bc910be5
Revises: 07dc3e6f8b82, b4c5d6e7f8a9
Create Date: 2026-11-05 18:06:21.366173

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05d2bc910be5'
down_revision: Union[str, None] = ('07dc3e6f8b82', 'b4c5d6e7f8a9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
