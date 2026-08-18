"""merge all current migration heads

Revision ID: 5c2e733ccfaa
Revises: 2f11224ed364, 75e9dc3ed8de, 9c49eaa4ce9a
Create Date: 2026-08-17 20:42:26.923225

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c2e733ccfaa'
down_revision: Union[str, None] = ('2f11224ed364', '75e9dc3ed8de', '9c49eaa4ce9a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
