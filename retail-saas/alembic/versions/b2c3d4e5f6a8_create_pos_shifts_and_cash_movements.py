"""create_pos_shifts_and_cash_movements

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-10-05 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "pos_shifts" not in tables:
        op.create_table(
            "pos_shifts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False, index=True),
            sa.Column("cashier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("opened_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
            sa.Column("opening_cash_float", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
            sa.Column("closing_cash_counted", sa.Numeric(12, 2), nullable=True),
            sa.Column("expected_cash", sa.Numeric(12, 2), nullable=True),
            sa.Column("cash_variance", sa.Numeric(12, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_pos_shifts_tenant_store_status",
            "pos_shifts",
            ["tenant_id", "store_id", "status"],
        )
        op.create_index(
            "ix_pos_shifts_cashier_status",
            "pos_shifts",
            ["tenant_id", "cashier_id", "status"],
        )

    if "pos_cash_movements" not in tables:
        op.create_table(
            "pos_cash_movements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("shift_id", sa.Integer(), sa.ForeignKey("pos_shifts.id"), nullable=False, index=True),
            sa.Column("movement_type", sa.String(30), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("reason", sa.String(255), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_pos_cash_movements_shift",
            "pos_cash_movements",
            ["tenant_id", "shift_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "pos_cash_movements" in tables:
        op.drop_table("pos_cash_movements")

    if "pos_shifts" in tables:
        op.drop_table("pos_shifts")

