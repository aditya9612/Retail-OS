"""create store_expenses table

Revision ID: 7d91c4e82f36
Revises: 5cb271a7a4ee
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d91c4e82f36"
down_revision: Union[str, None] = "5cb271a7a4ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_expenses",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "store_id",
            sa.Integer(),
            sa.ForeignKey(
                "stores.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "expense_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "payment_method",
            sa.String(50),
            nullable=True,
        ),
        sa.Column(
            "reference_number",
            sa.String(100),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_store_expenses_store_id",
        "store_expenses",
        ["store_id"],
    )

    op.create_index(
        "ix_store_expenses_category",
        "store_expenses",
        ["category"],
    )

    op.create_index(
        "ix_store_expenses_expense_date",
        "store_expenses",
        ["expense_date"],
    )

    op.create_index(
        "ix_store_expenses_reference_number",
        "store_expenses",
        ["reference_number"],
    )

    op.create_index(
        "ix_store_expenses_status",
        "store_expenses",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_store_expenses_status",
        table_name="store_expenses",
    )

    op.drop_index(
        "ix_store_expenses_reference_number",
        table_name="store_expenses",
    )

    op.drop_index(
        "ix_store_expenses_expense_date",
        table_name="store_expenses",
    )

    op.drop_index(
        "ix_store_expenses_category",
        table_name="store_expenses",
    )

    op.drop_index(
        "ix_store_expenses_store_id",
        table_name="store_expenses",
    )

    op.drop_table("store_expenses")
