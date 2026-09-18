"""add delivery methods table

Revision ID: 8f1e2d3c4b5a
Revises: 860afcdde201
Create Date: 2026-09-16 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f1e2d3c4b5a'
down_revision: Union[str, None] = '860afcdde201'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'delivery_methods',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('cost', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('estimated_days', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_delivery_method_tenant_code'),
    )
    op.create_index(op.f('ix_delivery_methods_tenant_id'), 'delivery_methods', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_delivery_methods_tenant_id'), table_name='delivery_methods')
    op.drop_table('delivery_methods')
