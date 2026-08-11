"""merge final alembic heads

Revision ID: 8b1d37df6083
Revises: 1f386b6d9d12, eb0c7cda81de
Create Date: 2026-08-07 18:01:57.125751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b1d37df6083'
down_revision: Union[str, None] = ('1f386b6d9d12', 'eb0c7cda81de')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
