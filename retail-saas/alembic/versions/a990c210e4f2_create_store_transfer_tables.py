"""create store transfer tables

Revision ID: a990c210e4f2
Revises: 7d91c4e82f36
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a990c210e4f2"
down_revision: Union[str, None] = "7d91c4e82f36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("store_transfers"):
        op.create_table(
            "store_transfers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("transfer_number", sa.String(length=100), nullable=False),
            sa.Column("source_store_id", sa.Integer(), nullable=False),
            sa.Column("destination_store_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["source_store_id"],
                ["stores.id"],
            ),
            sa.ForeignKeyConstraint(
                ["destination_store_id"],
                ["stores.id"],
            ),
            sa.ForeignKeyConstraint(
                ["approved_by"],
                ["users.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("transfer_number"),
        )

    if not inspector.has_table("store_transfer_items"):
        op.create_table(
            "store_transfer_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("transfer_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(
                ["transfer_id"],
                ["store_transfers.id"],
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("store_transfer_items"):
        op.drop_table("store_transfer_items")

    if inspector.has_table("store_transfers"):
        op.drop_table("store_transfers")