"""add_saas_plan_entitlements_and_tenant_current_subscription

Revision ID: 7b62ec7a8942
Revises: b74a887c60d8
Create Date: 2026-09-24 11:38:40.774133

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b62ec7a8942'
down_revision: Union[str, None] = 'b74a887c60d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CURRENT_STATUSES = ("trialing", "active", "past_due")


def upgrade() -> None:
    # -------------------------------------------------------------
    # 1. Create saas_plan_entitlements table
    # -------------------------------------------------------------
    op.create_table(
        'saas_plan_entitlements',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('dimension', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Integer(), nullable=True),
        sa.Column('is_unlimited', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['saas_plans.id'], name='fk_saas_plan_entitlements_plan_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'dimension', name='uq_plan_dimension'),
    )
    op.create_index('ix_saas_plan_entitlements_plan_id', 'saas_plan_entitlements', ['plan_id'], unique=False)

    # -------------------------------------------------------------
    # 2. Add tenants.current_subscription_id column
    # -------------------------------------------------------------
    op.add_column('tenants', sa.Column('current_subscription_id', sa.Integer(), nullable=True))

    # -------------------------------------------------------------
    # 3. Safe backfill for existing tenants
    # -------------------------------------------------------------
    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id, name FROM tenants")).fetchall()

    for t in tenants:
        t_id = t[0]
        t_name = t[1]
        subs = conn.execute(
            sa.text("SELECT id, tenant_id, status FROM saas_subscriptions WHERE tenant_id = :t_id"),
            {"t_id": t_id}
        ).fetchall()

        candidates = [s for s in subs if s[2] in CURRENT_STATUSES]
        if len(candidates) == 0:
            raise ValueError(f"Safe backfill failed: Tenant {t_id} ({t_name}) has 0 candidate subscriptions")
        if len(candidates) > 1:
            raise ValueError(f"Safe backfill failed: Tenant {t_id} ({t_name}) has {len(candidates)} ambiguous candidate subscriptions: {candidates}")

        sub_id, sub_tenant_id, sub_status = candidates[0]
        if sub_tenant_id != t_id:
            raise ValueError(f"Safe backfill failed: Cross-tenant mismatch! Sub {sub_id} tenant_id {sub_tenant_id} != Tenant {t_id}")

        conn.execute(
            sa.text("UPDATE tenants SET current_subscription_id = :sub_id WHERE id = :t_id"),
            {"sub_id": sub_id, "t_id": t_id}
        )

    # -------------------------------------------------------------
    # 4. Add index and foreign key on tenants.current_subscription_id
    # -------------------------------------------------------------
    op.create_index('ix_tenants_current_subscription_id', 'tenants', ['current_subscription_id'], unique=False)
    op.create_foreign_key(
        'fk_tenants_current_subscription_id',
        'tenants', 'saas_subscriptions',
        ['current_subscription_id'], ['id'],
        ondelete='SET NULL'
    )

    # -------------------------------------------------------------
    # 5. Composite Entitlement Usage Indexes
    # -------------------------------------------------------------
    op.create_index('ix_users_tenant_entitlement', 'users', ['tenant_id', 'is_deleted', 'is_active'], unique=False)
    op.create_index('ix_stores_tenant_entitlement', 'stores', ['tenant_id', 'is_active'], unique=False)
    op.create_index('ix_products_tenant_entitlement', 'products', ['tenant_id', 'is_active'], unique=False)
    op.create_index('ix_orders_tenant_billing', 'orders', ['tenant_id', 'created_at', 'status'], unique=False)
    op.create_index('ix_saas_subscriptions_tenant_lookup', 'saas_subscriptions', ['tenant_id', 'status', 'created_at', 'id'], unique=False)


def downgrade() -> None:
    # -------------------------------------------------------------
    # 1. Drop composite entitlement usage indexes
    # -------------------------------------------------------------
    op.drop_index('ix_saas_subscriptions_tenant_lookup', table_name='saas_subscriptions')
    op.drop_index('ix_orders_tenant_billing', table_name='orders')
    op.drop_index('ix_products_tenant_entitlement', table_name='products')
    op.drop_index('ix_stores_tenant_entitlement', table_name='stores')
    op.drop_index('ix_users_tenant_entitlement', table_name='users')

    # -------------------------------------------------------------
    # 2. Drop tenants.current_subscription_id FK, index, and column
    # -------------------------------------------------------------
    op.drop_constraint('fk_tenants_current_subscription_id', 'tenants', type_='foreignkey')
    op.drop_index('ix_tenants_current_subscription_id', table_name='tenants')
    op.drop_column('tenants', 'current_subscription_id')

    # -------------------------------------------------------------
    # 3. Drop saas_plan_entitlements table
    # -------------------------------------------------------------
    op.drop_index('ix_saas_plan_entitlements_plan_id', table_name='saas_plan_entitlements')
    op.drop_table('saas_plan_entitlements')
