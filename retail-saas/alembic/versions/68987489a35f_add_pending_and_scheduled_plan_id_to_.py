"""add_pending_and_scheduled_plan_id_to_saas_subscriptions

Revision ID: 68987489a35f
Revises: a6971df31751
Create Date: 2026-09-26 17:46:57.636280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68987489a35f'
down_revision: Union[str, None] = 'a6971df31751'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('saas_subscriptions', sa.Column('pending_plan_id', sa.Integer(), nullable=True))
    op.add_column('saas_subscriptions', sa.Column('scheduled_plan_id', sa.Integer(), nullable=True))
    op.create_index('ix_saas_subscriptions_pending_plan_id', 'saas_subscriptions', ['pending_plan_id'], unique=False)
    op.create_index('ix_saas_subscriptions_scheduled_plan_id', 'saas_subscriptions', ['scheduled_plan_id'], unique=False)
    op.create_foreign_key(
        'fk_saas_subscriptions_pending_plan_id',
        'saas_subscriptions', 'saas_plans',
        ['pending_plan_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_saas_subscriptions_scheduled_plan_id',
        'saas_subscriptions', 'saas_plans',
        ['scheduled_plan_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_saas_subscriptions_scheduled_plan_id', 'saas_subscriptions', type_='foreignkey')
    op.drop_constraint('fk_saas_subscriptions_pending_plan_id', 'saas_subscriptions', type_='foreignkey')
    op.drop_index('ix_saas_subscriptions_scheduled_plan_id', table_name='saas_subscriptions')
    op.drop_index('ix_saas_subscriptions_pending_plan_id', table_name='saas_subscriptions')
    op.drop_column('saas_subscriptions', 'scheduled_plan_id')
    op.drop_column('saas_subscriptions', 'pending_plan_id')
