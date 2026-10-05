"""add_pin_and_active_phone_to_users

Revision ID: 631e3011e13c
Revises: d8f2a1b3c4e5
Create Date: 2026-10-01 13:00:06.722203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '631e3011e13c'
down_revision: Union[str, None] = 'd8f2a1b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. pin_hash: VARCHAR(255), nullable=True
    op.add_column("users", sa.Column("pin_hash", sa.String(length=255), nullable=True))

    # 2. pin_set_at: DATETIME, nullable=True
    op.add_column("users", sa.Column("pin_set_at", sa.DateTime(), nullable=True))

    # 3. is_mobile_verified: BOOLEAN / TINYINT(1), nullable=False, default=False
    op.add_column(
        "users",
        sa.Column("is_mobile_verified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

    # 4. mobile_verified_at: DATETIME, nullable=True
    op.add_column("users", sa.Column("mobile_verified_at", sa.DateTime(), nullable=True))

    # 5. active_phone: generated virtual column VARCHAR(20)
    op.add_column(
        "users",
        sa.Column(
            "active_phone",
            sa.String(length=20),
            sa.Computed(
                "IF(is_deleted = 0 AND phone IS NOT NULL AND phone != '', phone, NULL)",
                persisted=False,
            ),
            nullable=True,
        ),
    )

    # 6. Add unique constraint: UNIQUE(tenant_id, active_phone)
    op.create_unique_constraint(
        "uq_users_tenant_active_phone",
        "users",
        ["tenant_id", "active_phone"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_tenant_active_phone", "users", type_="unique")
    op.drop_column("users", "active_phone")
    op.drop_column("users", "mobile_verified_at")
    op.drop_column("users", "is_mobile_verified")
    op.drop_column("users", "pin_set_at")
    op.drop_column("users", "pin_hash")

