"""merge latest migration heads

Revision ID: 412e696d6f93
Revises: 9599f1c1ddd1, c070896d644a
Create Date: 2026-09-29 19:09:38.544137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '412e696d6f93'
down_revision: Union[str, None] = ('9599f1c1ddd1', 'c070896d644a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
