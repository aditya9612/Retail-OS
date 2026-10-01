"""merge testing and gaurav feature alembic heads

Revision ID: a6971df31751
Revises: 7b62ec7a8942, c5969a57f245
Create Date: 2026-09-25 11:03:31.617697

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6971df31751'
down_revision: Union[str, None] = ('7b62ec7a8942', 'c5969a57f245')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
