"""seed_default_saas_plan_entitlements

Revision ID: d8f2a1b3c4e5
Revises: c7a1b2d3e4f5
Create Date: 2026-09-30 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f2a1b3c4e5'
down_revision: Union[str, None] = 'c7a1b2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ENTITLEMENTS = {
    'basic': [
        ('users', 5, False),
        ('stores', 1, False),
        ('products', 1000, False),
        ('monthly_orders', 500, False),
    ],
    'pro': [
        ('users', 20, False),
        ('stores', 5, False),
        ('products', 10000, False),
        ('monthly_orders', 5000, False),
    ],
    'enterprise': [
        ('users', None, True),
        ('stores', None, True),
        ('products', None, True),
        ('monthly_orders', None, True),
    ],
}


def upgrade() -> None:
    conn = op.get_bind()
    plans = conn.execute(sa.text("SELECT id, code FROM saas_plans")).fetchall()
    
    for plan_id, plan_code in plans:
        code = str(plan_code).strip().lower()
        if code in DEFAULT_ENTITLEMENTS:
            for dim, val, unlimited in DEFAULT_ENTITLEMENTS[code]:
                # Check if entitlement already exists
                existing = conn.execute(
                    sa.text(
                        "SELECT id FROM saas_plan_entitlements WHERE plan_id = :p_id AND dimension = :dim"
                    ),
                    {"p_id": plan_id, "dim": dim}
                ).fetchone()
                
                if not existing:
                    conn.execute(
                        sa.text(
                            "INSERT INTO saas_plan_entitlements (plan_id, dimension, value, is_unlimited, created_at, updated_at) "
                            "VALUES (:p_id, :dim, :val, :unlimited, NOW(), NOW())"
                        ),
                        {
                            "p_id": plan_id,
                            "dim": dim,
                            "val": val,
                            "unlimited": unlimited,
                        }
                    )


def downgrade() -> None:
    conn = op.get_bind()
    plans = conn.execute(sa.text("SELECT id, code FROM saas_plans")).fetchall()
    for plan_id, plan_code in plans:
        code = str(plan_code).strip().lower()
        if code in DEFAULT_ENTITLEMENTS:
            for dim, _, _ in DEFAULT_ENTITLEMENTS[code]:
                conn.execute(
                    sa.text(
                        "DELETE FROM saas_plan_entitlements WHERE plan_id = :p_id AND dimension = :dim"
                    ),
                    {"p_id": plan_id, "dim": dim}
                )

