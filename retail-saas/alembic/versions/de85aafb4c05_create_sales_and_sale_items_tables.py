"""create sales and sale_items tables

Revision ID: de85aafb4c05
Revises: a990c210e4f2
Create Date: 2026-09-21
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "de85aafb4c05"
down_revision: Union[str, None] = "a990c210e4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_offline = context.is_offline_mode()
    has_sales = False
    has_sale_items = False

    if not is_offline:
        inspector = inspect(bind)
        has_sales = inspector.has_table("sales")
        has_sale_items = inspector.has_table("sale_items")

    if not has_sales:
        op.create_table(
            "sales",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("invoice_number", sa.String(length=50), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("tax", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("payment_method", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["store_id"],
                ["stores.id"],
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["customers.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_sales_id"), "sales", ["id"], unique=False)
        op.create_index(op.f("ix_sales_store_id"), "sales", ["store_id"], unique=False)
        op.create_index(op.f("ix_sales_customer_id"), "sales", ["customer_id"], unique=False)
        op.create_index(op.f("ix_sales_invoice_number"), "sales", ["invoice_number"], unique=True)

    if not has_sale_items:
        op.create_table(
            "sale_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("tax", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("'0.00'")),
            sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.ForeignKeyConstraint(
                ["sale_id"],
                ["sales.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_sale_items_id"), "sale_items", ["id"], unique=False)
        op.create_index(op.f("ix_sale_items_sale_id"), "sale_items", ["sale_id"], unique=False)
        op.create_index(op.f("ix_sale_items_product_id"), "sale_items", ["product_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_offline = context.is_offline_mode()
    has_sales = True
    has_sale_items = True

    if not is_offline:
        inspector = inspect(bind)
        has_sales = inspector.has_table("sales")
        has_sale_items = inspector.has_table("sale_items")

    if has_sale_items:
        op.drop_index(op.f("ix_sale_items_product_id"), table_name="sale_items")
        op.drop_index(op.f("ix_sale_items_sale_id"), table_name="sale_items")
        op.drop_index(op.f("ix_sale_items_id"), table_name="sale_items")
        op.drop_table("sale_items")

    if has_sales:
        op.drop_index(op.f("ix_sales_invoice_number"), table_name="sales")
        op.drop_index(op.f("ix_sales_customer_id"), table_name="sales")
        op.drop_index(op.f("ix_sales_store_id"), table_name="sales")
        op.drop_index(op.f("ix_sales_id"), table_name="sales")
        op.drop_table("sales")
