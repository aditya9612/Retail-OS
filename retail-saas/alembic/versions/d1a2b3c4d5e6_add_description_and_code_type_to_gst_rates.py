"""add_description_and_code_type_to_gst_rates

Revision ID: d1a2b3c4d5e6
Revises: c4d5e6f7a8b9
Create Date: 2026-10-23 14:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd1a2b3c4d5e6'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "gst_rates" in tables:
        cols = [c["name"] for c in inspector.get_columns("gst_rates")]
        if "description" not in cols:
            op.add_column("gst_rates", sa.Column("description", sa.String(255), nullable=True))
        if "code_type" not in cols:
            op.add_column("gst_rates", sa.Column("code_type", sa.String(10), nullable=False, server_default="HSN"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "gst_rates" in tables:
        cols = [c["name"] for c in inspector.get_columns("gst_rates")]
        if "code_type" in cols:
            op.drop_column("gst_rates", "code_type")
        if "description" in cols:
            op.drop_column("gst_rates", "description")

