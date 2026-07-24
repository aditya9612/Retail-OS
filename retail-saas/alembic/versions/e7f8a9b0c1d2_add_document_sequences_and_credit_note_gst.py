"""Add document_sequences and credit note GST columns.

Revision ID: e7f8a9b0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "doc_type", "year", name="uq_document_sequences_tenant_type_year"
        ),
    )
    op.create_index(
        op.f("ix_document_sequences_tenant_id"),
        "document_sequences",
        ["tenant_id"],
        unique=False,
    )

    op.add_column(
        "credit_notes",
        sa.Column("cgst_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "credit_notes",
        sa.Column("sgst_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column(
        "credit_notes",
        sa.Column("igst_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
    )


def downgrade() -> None:
    op.drop_column("credit_notes", "igst_amount")
    op.drop_column("credit_notes", "sgst_amount")
    op.drop_column("credit_notes", "cgst_amount")
    op.drop_index(op.f("ix_document_sequences_tenant_id"), table_name="document_sequences")
    op.drop_table("document_sequences")
