"""make coupon code unique per tenant

Revision ID: 81f09a280edf
Revises: bcb2b204b637
Create Date: 2026-08-26 23:00:55.585229

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "81f09a280edf"
down_revision: Union[str, None] = "bcb2b204b637"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove old global unique index on coupon code
    op.drop_index(
        "code",
        table_name="coupons",
    )

    # Make coupon code unique per tenant
    op.create_unique_constraint(
        "uq_coupon_tenant_code",
        "coupons",
        ["tenant_id", "code"],
    )


def downgrade() -> None:
    # Remove tenant-wise unique constraint
    op.drop_constraint(
        "uq_coupon_tenant_code",
        "coupons",
        type_="unique",
    )

    # Restore global unique index on coupon code
    op.create_index(
        "code",
        "coupons",
        ["code"],
        unique=True,
    )