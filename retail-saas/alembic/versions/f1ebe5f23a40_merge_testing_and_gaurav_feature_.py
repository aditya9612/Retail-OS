"""merge testing and gaurav feature migration heads

Revision ID: f1ebe5f23a40
Revises: 05d2bc910be5, f4a5b6c7d8e9
Create Date: 2026-11-16 13:18:37.108399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1ebe5f23a40'
down_revision: Union[str, None] = ('05d2bc910be5', 'f4a5b6c7d8e9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
