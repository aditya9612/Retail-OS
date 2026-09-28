"""add_unique_constraint_to_saas_invoices_cycle

Revision ID: ec215d5db1fa
Revises: b9c77f46ab0c
Create Date: 2026-09-28 11:46:57.729523

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec215d5db1fa'
down_revision: Union[str, None] = 'b9c77f46ab0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_saas_invoice_cycle",
        "saas_invoices",
        ["subscription_id", "billing_reason", "due_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_saas_invoice_cycle",
        "saas_invoices",
        type_="unique",
    )
