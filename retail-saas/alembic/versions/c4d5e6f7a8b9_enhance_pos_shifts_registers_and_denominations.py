"""enhance_pos_shifts_registers_and_denominations

Revision ID: c4d5e6f7a8b9
Revises: 7a8b9c0d1e2f
Create Date: 2026-10-23 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = '7a8b9c0d1e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "pos_shifts" in tables:
        shift_cols = [c["name"] for c in inspector.get_columns("pos_shifts")]
        if "register_id" not in shift_cols:
            op.add_column("pos_shifts", sa.Column("register_id", sa.String(50), nullable=True))
            op.create_index("ix_pos_shifts_register_id", "pos_shifts", ["register_id"])
            op.create_index(
                "ix_pos_shifts_store_register_status",
                "pos_shifts",
                ["tenant_id", "store_id", "register_id", "status"],
            )
        if "opening_denominations" not in shift_cols:
            op.add_column("pos_shifts", sa.Column("opening_denominations", sa.JSON(), nullable=True))
        if "closing_denominations" not in shift_cols:
            op.add_column("pos_shifts", sa.Column("closing_denominations", sa.JSON(), nullable=True))
        if "closed_by" not in shift_cols:
            op.add_column("pos_shifts", sa.Column("closed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))

    if "payments" in tables:
        pay_cols = [c["name"] for c in inspector.get_columns("payments")]
        if "shift_id" not in pay_cols:
            op.add_column("payments", sa.Column("shift_id", sa.Integer(), sa.ForeignKey("pos_shifts.id"), nullable=True))
            op.create_index("ix_payments_shift_id", "payments", ["shift_id"])

    if "refunds" in tables:
        refund_cols = [c["name"] for c in inspector.get_columns("refunds")]
        if "shift_id" not in refund_cols:
            op.add_column("refunds", sa.Column("shift_id", sa.Integer(), sa.ForeignKey("pos_shifts.id"), nullable=True))
            op.create_index("ix_refunds_shift_id", "refunds", ["shift_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "refunds" in tables:
        refund_cols = [c["name"] for c in inspector.get_columns("refunds")]
        if "shift_id" in refund_cols:
            op.drop_index("ix_refunds_shift_id", table_name="refunds")
            op.drop_column("refunds", "shift_id")

    if "payments" in tables:
        pay_cols = [c["name"] for c in inspector.get_columns("payments")]
        if "shift_id" in pay_cols:
            op.drop_index("ix_payments_shift_id", table_name="payments")
            op.drop_column("payments", "shift_id")

    if "pos_shifts" in tables:
        shift_cols = [c["name"] for c in inspector.get_columns("pos_shifts")]
        if "register_id" in shift_cols:
            op.drop_index("ix_pos_shifts_store_register_status", table_name="pos_shifts")
            op.drop_index("ix_pos_shifts_register_id", table_name="pos_shifts")
            op.drop_column("pos_shifts", "register_id")
        if "opening_denominations" in shift_cols:
            op.drop_column("pos_shifts", "opening_denominations")
        if "closing_denominations" in shift_cols:
            op.drop_column("pos_shifts", "closing_denominations")
        if "closed_by" in shift_cols:
            op.drop_column("pos_shifts", "closed_by")

