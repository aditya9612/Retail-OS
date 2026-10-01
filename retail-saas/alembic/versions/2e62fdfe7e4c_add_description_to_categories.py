"""add_description_to_categories

Revision ID: 2e62fdfe7e4c
Revises: ec215d5db1fa
Create Date: 2026-10-01 18:35:55.235012

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e62fdfe7e4c'
down_revision: Union[str, None] = 'ec215d5db1fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("categories")]
    if "description" not in columns:
        op.add_column(
            "categories",
            sa.Column("description", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("categories")]
    if "description" in columns:
        op.drop_column("categories", "description")

