"""add updated_at to wallet transactions

Revision ID: 176cf1381b78
Revises: bc7a49751a24
Create Date: 2026-08-12 15:03:28.919713

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "176cf1381b78"
down_revision: Union[str, None] = "bc7a49751a24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [
        column["name"]
        for column in inspector.get_columns("wallet_transactions")
    ]

    if "updated_at" not in columns:
        op.add_column(
            "wallet_transactions",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=True,
            ),
        )

        op.execute(
            "UPDATE wallet_transactions "
            "SET updated_at = created_at "
            "WHERE updated_at IS NULL"
        )

        op.alter_column(
            "wallet_transactions",
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [
        column["name"]
        for column in inspector.get_columns("wallet_transactions")
    ]

    if "updated_at" in columns:
        op.drop_column("wallet_transactions", "updated_at")