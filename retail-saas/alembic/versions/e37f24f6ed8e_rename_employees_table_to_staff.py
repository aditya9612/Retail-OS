"""rename employees table to staff

Revision ID: e37f24f6ed8e
Revises: 2d3d64849e68
Create Date: 2026-08-18 14:17:25.440466

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e37f24f6ed8e'
down_revision: Union[str, None] = '2d3d64849e68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("employees", "staff")


def downgrade() -> None:
    op.rename_table("staff", "employees")