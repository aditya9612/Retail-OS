"""create_pos_held_carts_and_payment_tender

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-10-05 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "pos_held_carts" not in tables:
        op.create_table(
            "pos_held_carts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("hold_reference", sa.String(50), nullable=False, index=True),
            sa.Column("notes", sa.String(255), nullable=True),
            sa.Column("customer_name", sa.String(100), nullable=True),
            sa.Column("customer_phone", sa.String(20), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="held", index=True),
            sa.Column("items_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("gst_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("grand_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("same_state", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("cart_data", sa.JSON(), nullable=False),
            sa.Column("held_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("recalled_at", sa.DateTime(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_pos_held_carts_tenant_store_status",
            "pos_held_carts",
            ["tenant_id", "store_id", "status"],
        )
        op.create_index(
            "ix_pos_held_carts_tenant_ref",
            "pos_held_carts",
            ["tenant_id", "hold_reference"],
        )

    # Check payment columns
    if "payments" in tables:
        payment_columns = [col["name"] for col in inspector.get_columns("payments")]
        if "amount_tendered" not in payment_columns:
            op.add_column("payments", sa.Column("amount_tendered", sa.Numeric(12, 2), nullable=True))
        if "change_due" not in payment_columns:
            op.add_column("payments", sa.Column("change_due", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "payments" in tables:
        payment_columns = [col["name"] for col in inspector.get_columns("payments")]
        if "change_due" in payment_columns:
            op.drop_column("payments", "change_due")
        if "amount_tendered" in payment_columns:
            op.drop_column("payments", "amount_tendered")

    if "pos_held_carts" in tables:
        try:
            op.drop_index("ix_pos_held_carts_tenant_ref", table_name="pos_held_carts")
            op.drop_index("ix_pos_held_carts_tenant_store_status", table_name="pos_held_carts")
        except Exception:
            pass
        op.drop_table("pos_held_carts")

