"""add purchase order return tables

Revision ID: c053a70ef335
Revises: 7539023fd0ff
Create Date: 2026-09-03 13:27:12.837998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c053a70ef335"
down_revision: Union[str, None] = "7539023fd0ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "purchase_order_returns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="requested",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_purchase_order_returns_tenant_id",
        "purchase_order_returns",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "ix_purchase_order_returns_purchase_order_id",
        "purchase_order_returns",
        ["purchase_order_id"],
        unique=False,
    )

    op.create_index(
        "ix_purchase_order_returns_status",
        "purchase_order_returns",
        ["status"],
        unique=False,
    )

    op.create_table(
        "purchase_order_return_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("purchase_order_return_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_item_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "unit_price",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "total",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_order_return_id"],
            ["purchase_order_returns.id"],
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_item_id"],
            ["purchase_order_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_purchase_order_return_items_purchase_order_return_id",
        "purchase_order_return_items",
        ["purchase_order_return_id"],
        unique=False,
    )

    op.create_index(
        "ix_purchase_order_return_items_purchase_order_item_id",
        "purchase_order_return_items",
        ["purchase_order_item_id"],
        unique=False,
    )

    op.create_index(
        "ix_purchase_order_return_items_product_id",
        "purchase_order_return_items",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchase_order_return_items_product_id",
        table_name="purchase_order_return_items",
    )

    op.drop_index(
        "ix_purchase_order_return_items_purchase_order_item_id",
        table_name="purchase_order_return_items",
    )

    op.drop_index(
        "ix_purchase_order_return_items_purchase_order_return_id",
        table_name="purchase_order_return_items",
    )

    op.drop_table("purchase_order_return_items")

    op.drop_index(
        "ix_purchase_order_returns_status",
        table_name="purchase_order_returns",
    )

    op.drop_index(
        "ix_purchase_order_returns_purchase_order_id",
        table_name="purchase_order_returns",
    )

    op.drop_index(
        "ix_purchase_order_returns_tenant_id",
        table_name="purchase_order_returns",
    )

    op.drop_table("purchase_order_returns")