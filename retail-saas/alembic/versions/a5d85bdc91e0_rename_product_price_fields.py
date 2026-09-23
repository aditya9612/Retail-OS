"""rename product price fields

Revision ID: a5d85bdc91e0
Revises: a92528f55a80
Create Date: 2026-09-23 10:56:52.341213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5d85bdc91e0"
down_revision: Union[str, None] = "a92528f55a80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "price",
        new_column_name="selling_price",
        existing_type=sa.Numeric(12, 2),
        existing_nullable=False,
    )

    op.alter_column(
        "products",
        "cost_price",
        new_column_name="mrp",
        existing_type=sa.Numeric(12, 2),
        existing_nullable=True,
        existing_server_default=sa.text("0.00"),
    )


def downgrade() -> None:
    op.alter_column(
        "products",
        "selling_price",
        new_column_name="price",
        existing_type=sa.Numeric(12, 2),
        existing_nullable=False,
    )

    op.alter_column(
        "products",
        "mrp",
        new_column_name="cost_price",
        existing_type=sa.Numeric(12, 2),
        existing_nullable=True,
        existing_server_default=sa.text("0.00"),
    )