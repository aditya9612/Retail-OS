"""enhance customers credit limit and customer ledger entries

Revision ID: c4a1b2e3f5d6
Revises: f2a3b4c5d6e8
Create Date: 2026-10-22 14:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from decimal import Decimal


# revision identifiers, used by Alembic.
revision: str = "c4a1b2e3f5d6"
down_revision: Union[str, None] = "f2a3b4c5d6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("customers")}

    if "credit_limit" not in existing_cols:
        op.add_column(
            "customers",
            sa.Column(
                "credit_limit",
                sa.DECIMAL(12, 2),
                nullable=False,
                server_default="0.00",
            ),
        )
    if "outstanding_balance" not in existing_cols:
        op.add_column(
            "customers",
            sa.Column(
                "outstanding_balance",
                sa.DECIMAL(12, 2),
                nullable=False,
                server_default="0.00",
            ),
        )

    existing_tables = set(inspector.get_table_names())
    if "customer_ledger_entries" not in existing_tables:
        op.create_table(
            "customer_ledger_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
            sa.Column("entry_type", sa.String(20), nullable=False),
            sa.Column("amount", sa.DECIMAL(12, 2), nullable=False),
            sa.Column("balance_after", sa.DECIMAL(12, 2), nullable=False),
            sa.Column("reference_no", sa.String(100), nullable=True, index=True),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    if "customer_ledger_entries" in existing_tables:
        op.drop_table("customer_ledger_entries")

    existing_cols = {c["name"] for c in inspector.get_columns("customers")}
    if "outstanding_balance" in existing_cols:
        op.drop_column("customers", "outstanding_balance")
    if "credit_limit" in existing_cols:
        op.drop_column("customers", "credit_limit")
