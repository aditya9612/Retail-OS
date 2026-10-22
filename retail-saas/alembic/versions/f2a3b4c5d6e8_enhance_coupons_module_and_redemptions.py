"""enhance coupons module and redemptions

Revision ID: f2a3b4c5d6e8
Revises: f124c4bb8654
Create Date: 2026-10-22 11:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e8"
down_revision: Union[str, None] = "f124c4bb8654"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to coupons table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("coupons")}

    if "usage_limit_per_customer" not in existing_cols:
        op.add_column("coupons", sa.Column("usage_limit_per_customer", sa.Integer(), nullable=True, server_default="1"))
    if "applicable_categories" not in existing_cols:
        op.add_column("coupons", sa.Column("applicable_categories", sa.JSON(), nullable=True))
    if "applicable_products" not in existing_cols:
        op.add_column("coupons", sa.Column("applicable_products", sa.JSON(), nullable=True))
    if "store_id" not in existing_cols:
        op.add_column("coupons", sa.Column("store_id", sa.Integer(), nullable=True))
        try:
            op.create_foreign_key("fk_coupons_store_id", "coupons", "stores", ["store_id"], ["id"])
        except Exception:
            pass
    if "first_order_only" not in existing_cols:
        op.add_column("coupons", sa.Column("first_order_only", sa.Boolean(), nullable=False, server_default="0"))
    if "is_deleted" not in existing_cols:
        op.add_column("coupons", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"))

    # 2. Create coupon_redemptions table if not exists
    existing_tables = set(inspector.get_table_names())
    if "coupon_redemptions" not in existing_tables:
        op.create_table(
            "coupon_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("coupon_id", sa.Integer(), sa.ForeignKey("coupons.id"), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True, index=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("customer_phone", sa.String(20), nullable=True, index=True),
            sa.Column("discount_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
            sa.Column("order_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
            sa.Column("redeemed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    try:
        op.drop_table("coupon_redemptions")
    except Exception:
        pass

