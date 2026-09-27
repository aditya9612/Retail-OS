"""make_customer_email_and_phone_unique_per_tenant

Revision ID: b9c77f46ab0c
Revises: 68987489a35f
Create Date: 2026-09-27 15:53:15.437217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9c77f46ab0c'
down_revision: Union[str, None] = '68987489a35f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove old global unique indexes on customer email and phone
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_index(op.f('ix_customers_phone'), table_name='customers')

    # Re-create normal non-unique lookup indexes
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=False)
    op.create_index(op.f('ix_customers_phone'), 'customers', ['phone'], unique=False)

    # Create tenant-scoped composite unique constraints
    op.create_unique_constraint(
        'uq_customer_tenant_phone',
        'customers',
        ['tenant_id', 'phone'],
    )
    op.create_unique_constraint(
        'uq_customer_tenant_email',
        'customers',
        ['tenant_id', 'email'],
    )


def downgrade() -> None:
    # Remove tenant-scoped composite unique constraints
    op.drop_constraint('uq_customer_tenant_email', 'customers', type_='unique')
    op.drop_constraint('uq_customer_tenant_phone', 'customers', type_='unique')

    # Drop non-unique indexes
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_index(op.f('ix_customers_phone'), table_name='customers')

    # Restore global unique indexes
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=True)
    op.create_index(op.f('ix_customers_phone'), 'customers', ['phone'], unique=True)
