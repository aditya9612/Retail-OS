"""add variant_id to order_items

Revision ID: 06b_add_order_items_variant_id
Revises: d164abefdf3c
Create Date: 2026-10-06 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '06b_add_order_items_variant_id'
down_revision = 'e8f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_items",
        sa.Column("variant_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_order_items_variant_id",
        "order_items",
        ["variant_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_order_items_variant_id",
        "order_items",
        "product_variants",
        ["variant_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_order_items_variant_id",
        "order_items",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_order_items_variant_id",
        table_name="order_items",
    )
    op.drop_column("order_items", "variant_id")

