"""enhance order returns with items, restocking, and workflow

Revision ID: 7a8b9c0d1e2f
Revises: c4a1b2e3f5d6
Create Date: 2026-10-22 17:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, None] = "c4a1b2e3f5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # 1. Enhance order_returns table columns
    if "order_returns" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("order_returns")}

        if "return_number" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column("return_number", sa.String(50), nullable=True),
            )
            try:
                op.create_index(
                    "ix_order_returns_return_number",
                    "order_returns",
                    ["return_number"],
                    unique=True,
                )
            except Exception:
                pass

        if "return_type" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "return_type",
                    sa.String(30),
                    nullable=False,
                    server_default="refund",
                ),
            )

        if "total_amount" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "total_amount",
                    sa.DECIMAL(12, 2),
                    nullable=False,
                    server_default="0.00",
                ),
            )

        if "refund_amount" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "refund_amount",
                    sa.DECIMAL(12, 2),
                    nullable=False,
                    server_default="0.00",
                ),
            )

        if "exchange_order_id" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "exchange_order_id",
                    sa.Integer(),
                    sa.ForeignKey("orders.id"),
                    nullable=True,
                ),
            )
            try:
                op.create_index(
                    "ix_order_returns_exchange_order_id",
                    "order_returns",
                    ["exchange_order_id"],
                )
            except Exception:
                pass

        if "created_by_id" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "created_by_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            )

        if "approved_by_id" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "approved_by_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            )

        if "approved_at" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column("approved_at", sa.DateTime(), nullable=True),
            )

        if "rejected_by_id" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "rejected_by_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            )

        if "rejected_at" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column("rejected_at", sa.DateTime(), nullable=True),
            )

        if "rejection_reason" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column("rejection_reason", sa.Text(), nullable=True),
            )

        if "completed_by_id" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column(
                    "completed_by_id",
                    sa.Integer(),
                    sa.ForeignKey("users.id"),
                    nullable=True,
                ),
            )

        if "completed_at" not in existing_cols:
            op.add_column(
                "order_returns",
                sa.Column("completed_at", sa.DateTime(), nullable=True),
            )

    # 2. Create order_return_items table
    if "order_return_items" not in existing_tables:
        op.create_table(
            "order_return_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("order_return_id", sa.Integer(), sa.ForeignKey("order_returns.id"), nullable=False, index=True),
            sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=False, index=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price", sa.DECIMAL(12, 2), nullable=False, server_default="0.00"),
            sa.Column("total_amount", sa.DECIMAL(12, 2), nullable=False, server_default="0.00"),
            sa.Column("condition", sa.String(30), nullable=False, server_default="sellable"),
            sa.Column("reason", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "order_return_items" in existing_tables:
        op.drop_table("order_return_items")

    if "order_returns" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("order_returns")}
        for col in [
            "completed_at",
            "completed_by_id",
            "rejection_reason",
            "rejected_at",
            "rejected_by_id",
            "approved_at",
            "approved_by_id",
            "created_by_id",
            "exchange_order_id",
            "refund_amount",
            "total_amount",
            "return_type",
            "return_number",
        ]:
            if col in existing_cols:
                op.drop_column("order_returns", col)
