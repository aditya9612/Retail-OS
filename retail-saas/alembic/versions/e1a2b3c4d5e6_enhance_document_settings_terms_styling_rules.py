"""enhance_document_settings_terms_styling_rules

Revision ID: e1a2b3c4d5e6
Revises: c1a2b3c4d5e6
Create Date: 2026-10-23 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, None] = 'c1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "document_settings" in tables:
        cols = [c["name"] for c in inspector.get_columns("document_settings")]
        if "terms_and_conditions" not in cols:
            op.add_column("document_settings", sa.Column("terms_and_conditions", sa.Text(), nullable=True))
        if "padding_length" not in cols:
            op.add_column("document_settings", sa.Column("padding_length", sa.Integer(), nullable=False, server_default="6"))
        if "primary_color" not in cols:
            op.add_column("document_settings", sa.Column("primary_color", sa.String(20), nullable=True, server_default="#1E3A8A"))
        if "secondary_color" not in cols:
            op.add_column("document_settings", sa.Column("secondary_color", sa.String(20), nullable=True, server_default="#059669"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "document_settings" in tables:
        cols = [c["name"] for c in inspector.get_columns("document_settings")]
        if "secondary_color" in cols:
            op.drop_column("document_settings", "secondary_color")
        if "primary_color" in cols:
            op.drop_column("document_settings", "primary_color")
        if "padding_length" in cols:
            op.drop_column("document_settings", "padding_length")
        if "terms_and_conditions" in cols:
            op.drop_column("document_settings", "terms_and_conditions")

