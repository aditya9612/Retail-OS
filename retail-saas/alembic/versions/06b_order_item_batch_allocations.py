"""create order item batch allocations table

Revision ID: 06b_order_item_batch_allocations
Revises: 06a_batch_allocation_idx
Create Date: 2026-10-06 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '06b_order_item_batch_allocations'
down_revision = '06a_batch_allocation_idx'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_item_batch_allocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_item_id",
            sa.Integer(),
            sa.ForeignKey("order_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("product_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_oiba_order_item_id",
        "order_item_batch_allocations",
        ["order_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_oiba_batch_id",
        "order_item_batch_allocations",
        ["batch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("order_item_batch_allocations")

