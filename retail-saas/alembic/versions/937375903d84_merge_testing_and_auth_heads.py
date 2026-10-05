"""merge_testing_and_auth_heads

Revision ID: 937375903d84
Revises: 625d985f22e2, b0621e5f93f9
Create Date: 2026-10-02 00:59:20.968051

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '937375903d84'
down_revision: Union[str, None] = ('625d985f22e2', 'b0621e5f93f9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
